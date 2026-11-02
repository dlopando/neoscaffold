"""Social Studio accounts, distribution, encryption, adapters, and the queue.

HTTP is mocked. No test calls TikTok, Meta, X, Google, or LinkedIn.
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from custom_extensions.social_studio import captions, pages
from custom_extensions.social_studio.build_workflow import build_workflow
from custom_extensions.social_studio.crypto import (
    CryptoError,
    decrypt,
    encrypt,
    plaintext_in_ciphertext,
)
from custom_extensions.social_studio.distribute import build_plan
from custom_extensions.social_studio.extension import (
    SocialAccountSelect,
    SocialCaptionVariations,
    SocialDistribute,
    SocialPostLog,
)
from custom_extensions.social_studio.paths import example_workflow_path
from custom_extensions.social_studio.platforms.base import (
    HTTPResponse,
    MediaSource,
    PlatformError,
    PlatformNotImplemented,
    TokenBundle,
)
from custom_extensions.social_studio.platforms.facebook import FacebookAdapter
from custom_extensions.social_studio.platforms.instagram import InstagramAdapter
from custom_extensions.social_studio.platforms.linkedin import LinkedInAdapter
from custom_extensions.social_studio.platforms.registry import get_adapter
from custom_extensions.social_studio.platforms.tiktok import TikTokAdapter
from custom_extensions.social_studio.platforms.x import XAdapter, pkce_challenge
from custom_extensions.social_studio.platforms.youtube import YouTubeAdapter
from custom_extensions.social_studio.scheduler import execute_post, shift, tick
from custom_extensions.social_studio.store import SocialStore, expiry_from_seconds, get_store


SECRET = "test-secret-key"
TOKEN = "super-secret-token-value"


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _response(status=200, payload=None, headers=None, content=None):
    if content is None:
        content = json.dumps(payload or {}).encode("utf-8")
    return HTTPResponse(status, headers or {}, content, "https://example.test/path")


def _inputs(required=None, optional=None):
    def pack(values):
        return {key: {"values": value} for key, value in (values or {}).items()}

    return {"required_inputs": pack(required), "optional_inputs": pack(optional)}


def _creative(index, aspect="1:1", kind="image"):
    return {
        "style_id": f"style-{index}",
        "style_name": f"Style {index}",
        "headline": f"Headline {index}",
        "image_path": f"/tmp/ad-{index}.png",
        "image_url": f"https://cdn.example/ad-{index}.png",
        "aspect": aspect,
        "width": 1080,
        "height": 1080 if aspect == "1:1" else 1920,
        "media_kind": kind,
        "placeholder": True,
        "size_bytes": 1200,
    }


def _account(platform, handle, account_id=None, audited=False):
    return {
        "id": account_id or platform + "-id",
        "platform": platform,
        "handle": handle,
        "display_name": handle,
        "tags": ["luma"],
        "extra": {"tiktok_audited": audited},
    }


def _media(path, kind="image", url=""):
    return MediaSource(
        path=path,
        url=url,
        kind=kind,
        mime="image/jpeg" if kind == "image" else "video/mp4",
        filename=os.path.basename(path),
    )


def _touch(path, payload=b"bytes"):
    path.write_bytes(payload)
    return str(path)


# --- encryption and store ---


def test_encrypt_roundtrip_and_missing_key():
    env = {"SOCIAL_STUDIO_SECRET_KEY": SECRET}
    blob = encrypt(TOKEN, env)
    assert decrypt(blob, env) == TOKEN
    assert not plaintext_in_ciphertext(TOKEN, blob)
    assert TOKEN not in blob
    with pytest.raises(CryptoError):
        decrypt(blob, {"SOCIAL_STUDIO_SECRET_KEY": "other-key"})
    with pytest.raises(CryptoError):
        encrypt(TOKEN, {})


def test_tokens_are_encrypted_at_rest_and_hidden_from_public_rows(tmp_path):
    store = SocialStore(str(tmp_path / "social.db"))
    os.environ["SOCIAL_STUDIO_SECRET_KEY"] = SECRET
    try:
        created = store.upsert_account(
            platform="x",
            handle="@luma",
            display_name="Luma",
            external_id="user-1",
            tags=["luma", "launch"],
            access_token=TOKEN,
            refresh_token="refresh-secret-value",
            token_expiry="2099-01-01T00:00:00Z",
        )
        raw = (tmp_path / "social.db").read_bytes()
        assert TOKEN.encode() not in raw
        assert b"refresh-secret-value" not in raw
        public = json.dumps(store.get_account(created["id"]))
        assert "access_token" not in json.loads(public)
        assert TOKEN not in public
        secret = store.get_account(created["id"], include_secrets=True)
        assert secret["access_token"] == TOKEN
        assert secret["refresh_token"] == "refresh-secret-value"
        reopened = SocialStore(str(tmp_path / "social.db"))
        again = reopened.get_account(created["id"], include_secrets=True)
        assert again["access_token"] == TOKEN
        assert again["tags"] == ["luma", "launch"]
    finally:
        os.environ.pop("SOCIAL_STUDIO_SECRET_KEY", None)


def test_tag_group_and_reconnect_updates_same_external_id(tmp_path):
    os.environ["SOCIAL_STUDIO_SECRET_KEY"] = SECRET
    try:
        store = SocialStore(str(tmp_path / "social.db"))
        first = store.upsert_account(
            platform="instagram",
            handle="@old",
            display_name="Old",
            external_id="ig-1",
            access_token="first-token-value",
            tags=["skincare"],
        )
        second = store.upsert_account(
            platform="instagram",
            handle="@new",
            display_name="New",
            external_id="ig-1",
            access_token="second-token-value",
            tags=["skincare"],
        )
        assert first["id"] == second["id"]
        assert second["handle"] == "@new"
        assert store.get_account(first["id"], include_secrets=True)["access_token"] == (
            "second-token-value"
        )
        grouped = store.add_tag(first["id"], "launch")
        assert grouped["tags"] == ["skincare", "launch"]
        assert store.list_accounts(tag="launch")[0]["id"] == first["id"]
        store.remove_account(first["id"])
        assert store.list_accounts() == []
    finally:
        os.environ.pop("SOCIAL_STUDIO_SECRET_KEY", None)


# --- distribution ---


def test_round_robin_stagger_and_distinct_captions():
    creatives = [_creative(0), _creative(1), _creative(2), _creative(3)]
    accounts = [_account("tiktok", "@a", "a"), _account("x", "@b", "b")]
    captions_table = [
        {"creative_index": index, "variants": [f"line-{index}-A", f"line-{index}-B"]}
        for index in range(4)
    ]
    plan = build_plan(
        creatives,
        accounts,
        captions_table,
        strategy="round-robin",
        dry_run=True,
        schedule_at="2026-11-02T18:00:00Z",
        stagger_seconds=90,
        jitter_seconds=0,
        privacy="public",
        seed=1,
    )
    assert plan["dry_run"] is True
    assert [item["account_id"] for item in plan["items"]] == ["a", "b", "a", "b"]
    assert [item["caption"] for item in plan["items"]] == [
        "line-0-A",
        "line-1-B",
        "line-2-A",
        "line-3-B",
    ]
    assert plan["items"][0]["scheduled_at"] == "2026-11-02T18:00:00Z"
    assert plan["items"][2]["scheduled_at"] == "2026-11-02T18:01:30Z"
    assert plan["items"][0]["status"] == "dry_run"
    assert any("SELF_ONLY" in warning for warning in plan["items"][0]["warnings"])
    assert plan["items"][0]["privacy"] == "SELF_ONLY"


def test_random_is_deterministic_and_does_not_repeat_a_creative():
    creatives = [_creative(index) for index in range(4)]
    accounts = [_account("facebook", f"@p{index}", f"id-{index}") for index in range(3)]
    sequences = []
    for seed in range(8):
        plan = build_plan(
            creatives,
            accounts,
            strategy="random",
            dry_run=True,
            schedule_at="2026-11-02T18:00:00Z",
            seed=seed,
        )
        indexes = [item["creative_index"] for item in plan["items"]]
        assert sorted(indexes) == [0, 1, 2, 3]
        pairs = [(item["creative_index"], item["account_id"]) for item in plan["items"]]
        assert len(pairs) == len(set(pairs))
        sequences.append(tuple(item["account_id"] for item in plan["items"]))
    again = build_plan(
        creatives,
        accounts,
        strategy="random",
        dry_run=True,
        schedule_at="2026-11-02T18:00:00Z",
        seed=3,
    )
    assert tuple(item["account_id"] for item in again["items"]) == sequences[3]
    assert len(set(sequences)) > 1


def test_all_to_all_gives_each_account_a_different_caption():
    captions_table = [
        {"creative_index": 0, "variants": ["alpha", "beta"]},
        {"creative_index": 1, "variants": ["gamma", "delta"]},
    ]
    plan = build_plan(
        [_creative(0), _creative(1)],
        [_account("linkedin", "Member", "m"), _account("facebook", "Page", "p")],
        captions_table,
        strategy="all-to-all",
        dry_run=True,
        schedule_at="2026-11-02T18:00:00Z",
        stagger_seconds=30,
        jitter_seconds=0,
    )
    assert len(plan["items"]) == 4
    first_creative = [item for item in plan["items"] if item["creative_index"] == 0]
    assert {item["caption"] for item in first_creative} == {"alpha", "beta"}
    assert {item["scheduled_at"] for item in first_creative} == {"2026-11-02T18:00:00Z"}
    member_times = [item["scheduled_at"] for item in plan["items"] if item["account_id"] == "m"]
    assert member_times == ["2026-11-02T18:00:00Z", "2026-11-02T18:00:30Z"]


def test_constraints_skip_youtube_stills_and_oversized_files():
    plan = build_plan(
        [_creative(0, aspect="1:1"), _creative(1, aspect="9:16")],
        [_account("youtube", "@channel", "yt"), _account("tiktok", "@tok", "tt")],
        strategy="all-to-all",
        dry_run=True,
        schedule_at="2026-11-02T18:00:00Z",
    )
    skipped = [item for item in plan["items"] if item["platform"] == "youtube"]
    assert skipped
    assert all(item["status"] == "skipped" for item in skipped)
    assert "still images" in skipped[0]["skip_reason"]
    huge = _creative(2)
    huge["size_bytes"] = 50 * 1024 * 1024
    huge_plan = build_plan(
        [huge],
        [_account("x", "@luma", "x1")],
        strategy="round-robin",
        dry_run=True,
        schedule_at="2026-11-02T18:00:00Z",
    )
    assert huge_plan["items"][0]["status"] == "skipped"
    assert "limit" in huge_plan["items"][0]["skip_reason"]


def test_keeps_favorites_and_drops_discarded():
    creatives = [
        dict(_creative(0), favorite=True),
        dict(_creative(1), favorite=False),
        dict(_creative(2), favorite=True, discarded=True),
    ]
    kept = build_plan(
        creatives,
        [_account("facebook", "Page", "p")],
        strategy="round-robin",
        dry_run=True,
        include="favorites_only",
        schedule_at="2026-11-02T18:00:00Z",
    )
    assert [item["creative_index"] for item in kept["items"]] == [0]


def test_jitter_is_bounded_per_account():
    plan = build_plan(
        [_creative(0), _creative(1)],
        [_account("x", "@luma", "x1")],
        strategy="round-robin",
        dry_run=True,
        schedule_at="2026-11-02T18:00:00Z",
        stagger_seconds=10,
        jitter_seconds=5,
        seed=1,
    )
    import random

    extra = random.Random(1).randint(0, 5)
    start = datetime(2026, 11, 2, 18, 0, tzinfo=timezone.utc)
    expected = (start + timedelta(seconds=10 + extra)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert plan["items"][1]["scheduled_at"] == expected


def test_heuristic_captions_and_text_model(monkeypatch):
    creative = {"style_name": "Claymation", "headline": "Luma Serum"}
    lines, label = captions.generate_captions(
        creative, count=3, tone="witty", brief={"product_name": "Luma Serum", "claims": ["fragrance free"]}
    )
    assert label == "heuristic"
    assert len(lines) == 3
    assert all("Luma Serum" in line for line in lines)
    assert any("#" in line for line in lines)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("AD_STUDIO_TEXT_MODEL", "gpt-test")
    monkeypatch.setattr(
        captions,
        "_call_text_model",
        lambda prompt: '["One caption #Luma", "Two caption #Ad", "Three caption #New"]',
    )
    modeled, model = captions.generate_captions(creative, count=3, use_model="yes")
    assert model == "gpt-test"
    assert modeled[0].startswith("One caption")


# --- adapters ---


def test_http_errors_do_not_include_query_secrets():
    response = HTTPResponse(
        400,
        {},
        b'{"error":"bad"}',
        "https://graph.facebook.com/oauth/access_token?client_secret=super-secret&code=1",
    )
    with pytest.raises(PlatformError) as caught:
        response.raise_for_status()
    assert "super-secret" not in str(caught.value)


def test_tiktok_photo_publish_forces_self_only_until_audit(tmp_path):
    transport = FakeTransport(
        [
            _response(payload={"data": {"publish_id": "photo-1"}, "error": {"code": "ok"}}),
        ]
    )
    adapter = TikTokAdapter(transport=transport, env={"TIKTOK_CONTENT_POSTING_AUDITED": "false"})
    result = adapter.publish(
        {"access_token": TOKEN},
        _media(str(tmp_path / "a.jpg"), url="https://cdn.example/a.jpg"),
        "A private caption",
        {"privacy": "PUBLIC_TO_EVERYONE"},
    )
    body = transport.calls[0]["json_body"]
    assert transport.calls[0]["url"].endswith("/post/publish/content/init/")
    assert body["post_info"]["privacy_level"] == "SELF_ONLY"
    assert body["source_info"]["source"] == "PULL_FROM_URL"
    assert result.remote_id == "photo-1"
    assert result.warnings
    audited = TikTokAdapter(
        transport=FakeTransport(
            [_response(payload={"data": {"publish_id": "photo-2"}, "error": {"code": "ok"}})]
        ),
        env={"TIKTOK_CONTENT_POSTING_AUDITED": "true"},
    )
    audited.publish(
        {"access_token": TOKEN},
        _media(str(tmp_path / "b.jpg"), url="https://cdn.example/b.jpg"),
        "Public",
        {"privacy": "PUBLIC_TO_EVERYONE"},
    )
    assert audited.transport.calls[0]["json_body"]["post_info"]["privacy_level"] == "PUBLIC_TO_EVERYONE"


def test_tiktok_video_upload_and_status(tmp_path):
    video = _touch(tmp_path / "clip.mp4", b"video-bytes")
    transport = FakeTransport(
        [
            _response(
                payload={
                    "data": {"publish_id": "vid-1", "upload_url": "https://upload.tiktok.test/put"},
                    "error": {"code": "ok"},
                }
            ),
            _response(payload={}),
            _response(payload={"data": {"status": "PUBLISH_COMPLETE"}, "error": {"code": "ok"}}),
        ]
    )
    adapter = TikTokAdapter(transport=transport, env={})
    result = adapter.publish(
        {"access_token": TOKEN},
        _media(video, kind="video"),
        "Short",
        {"privacy": "SELF_ONLY"},
    )
    assert transport.calls[0]["url"].endswith("/video/init/")
    assert transport.calls[1]["method"] == "PUT"
    assert transport.calls[1]["url"] == "https://upload.tiktok.test/put"
    assert result.remote_id == "vid-1"
    status = adapter.get_status({"access_token": TOKEN}, "vid-1")
    assert status["status"] == "PUBLISH_COMPLETE"
    assert TOKEN not in json.dumps(transport.calls[0]["json_body"])


def test_instagram_container_publish(tmp_path):
    transport = FakeTransport(
        [
            _response(payload={"id": "container-1"}),
            _response(payload={"id": "ig-post-9"}),
        ]
    )
    adapter = InstagramAdapter(transport=transport, env={})
    result = adapter.publish(
        {"access_token": TOKEN, "external_id": "1789", "extra": {"ig_user_id": "1789"}},
        _media(str(tmp_path / "a.jpg"), url="https://cdn.example/a.jpg"),
        "Caption",
    )
    assert transport.calls[0]["url"].endswith("/1789/media")
    assert transport.calls[0]["data"]["image_url"] == "https://cdn.example/a.jpg"
    assert transport.calls[1]["url"].endswith("/1789/media_publish")
    assert transport.calls[1]["data"]["creation_id"] == "container-1"
    assert result.remote_id == "ig-post-9"
    with pytest.raises(PlatformError):
        adapter.publish(
            {"access_token": TOKEN, "extra": {"ig_user_id": "1789"}},
            _media(str(tmp_path / "local.jpg")),
            "No public URL",
        )


def test_facebook_page_photo_upload(tmp_path):
    image = _touch(tmp_path / "page.jpg", b"jpeg-bytes")
    transport = FakeTransport([_response(payload={"id": "photo-1", "post_id": "page_post"})])
    adapter = FacebookAdapter(transport=transport, env={})
    result = adapter.publish(
        {"access_token": TOKEN, "external_id": "99", "extra": {"page_id": "99"}},
        _media(image),
        "Page caption",
        {"privacy": "PUBLISHED"},
    )
    assert transport.calls[0]["url"].endswith("/99/photos")
    filename, content, mime = transport.calls[0]["files"]["source"]
    assert filename == "page.jpg"
    assert content == b"jpeg-bytes"
    assert result.remote_id == "page_post"


def test_x_pkce_upload_and_post(tmp_path):
    image = _touch(tmp_path / "post.jpg", b"jpeg")
    challenge = pkce_challenge("verifier-value")
    adapter = XAdapter(
        transport=FakeTransport([]),
        env={"X_CLIENT_ID": "cid", "X_CLIENT_SECRET": "csecret"},
    )
    url = adapter.authorization_url("state-1", "https://app.example/callback", challenge)
    assert "code_challenge=" in url
    assert "S256" in url
    assert "cid" in url
    transport = FakeTransport(
        [
            _response(payload={"data": {"id": "media-7"}}),
            _response(payload={"data": {"id": "tweet-8"}}),
        ]
    )
    adapter.transport = transport
    result = adapter.publish(
        {"access_token": TOKEN, "handle": "@luma"},
        _media(image),
        "Hello",
    )
    assert transport.calls[0]["url"].endswith("/2/media/upload")
    assert transport.calls[1]["json_body"]["media"]["media_ids"] == ["media-7"]
    assert result.remote_id == "tweet-8"
    assert result.permalink == "https://x.com/luma/status/tweet-8"
    exchange = XAdapter(
        transport=FakeTransport(
            [_response(payload={"access_token": "aaa", "refresh_token": "rrr", "expires_in": 7200})]
        ),
        env={"X_CLIENT_ID": "cid", "X_CLIENT_SECRET": "csecret"},
    )
    bundle = exchange.exchange_code("code", "https://app.example/callback", "verifier-value")
    assert bundle.access_token == "aaa"
    assert exchange.transport.calls[0]["data"]["code_verifier"] == "verifier-value"
    assert "csecret" not in json.dumps(exchange.transport.calls[0]["data"])


def test_youtube_rejects_images_and_uploads_video(tmp_path):
    adapter = YouTubeAdapter(transport=FakeTransport([]), env={})
    with pytest.raises(PlatformNotImplemented) as caught:
        adapter.publish({"access_token": TOKEN}, _media(str(tmp_path / "still.jpg")), "Still")
    assert "still images" in str(caught.value).lower()
    assert adapter.transport.calls == []
    video = _touch(tmp_path / "short.mp4", b"mp4")
    transport = FakeTransport(
        [
            _response(headers={"Location": "https://upload.youtube.test/session"}),
            _response(payload={"id": "vid123"}),
        ]
    )
    adapter.transport = transport
    result = adapter.publish(
        {"access_token": TOKEN},
        _media(video, kind="video"),
        "A short",
        {"privacy": "public"},
    )
    assert "uploadType" in transport.calls[0]["params"]["uploadType"] or transport.calls[0]["params"]["uploadType"] == "resumable"
    assert "#Shorts" in transport.calls[0]["json_body"]["snippet"]["description"]
    assert transport.calls[1]["method"] == "PUT"
    assert transport.calls[1]["url"] == "https://upload.youtube.test/session"
    assert result.permalink == "https://www.youtube.com/shorts/vid123"


def test_linkedin_image_post_and_video_not_implemented(tmp_path):
    image = _touch(tmp_path / "li.jpg", b"jpeg")
    transport = FakeTransport(
        [
            _response(
                payload={
                    "value": {
                        "uploadUrl": "https://upload.linkedin.test/img",
                        "image": "urn:li:image:1",
                    }
                }
            ),
            _response(status=201, payload={}),
            _response(status=201, payload={}, headers={"x-restli-id": "urn:li:share:5"}),
        ]
    )
    adapter = LinkedInAdapter(transport=transport, env={"LINKEDIN_API_VERSION": "202410"})
    result = adapter.publish(
        {
            "access_token": TOKEN,
            "extra": {"author": "urn:li:person:abc", "person_id": "abc"},
        },
        _media(image),
        "Member post",
        {"privacy": "PUBLIC"},
    )
    assert "initializeUpload" in transport.calls[0]["url"]
    assert transport.calls[0]["json_body"]["initializeUploadRequest"]["owner"] == "urn:li:person:abc"
    assert transport.calls[1]["method"] == "PUT"
    assert transport.calls[2]["json_body"]["content"]["media"]["id"] == "urn:li:image:1"
    assert result.remote_id == "urn:li:share:5"
    with pytest.raises(PlatformNotImplemented):
        adapter.publish(
            {"access_token": TOKEN, "extra": {"author": "urn:li:person:abc"}},
            _media(str(tmp_path / "clip.mp4"), kind="video"),
            "Video",
        )


def test_oauth_urls_use_client_ids():
    tiktok = TikTokAdapter(env={"TIKTOK_CLIENT_KEY": "tt-key", "TIKTOK_CLIENT_SECRET": "tt-secret"})
    url = tiktok.authorization_url("st", "https://app.example/tiktok")
    assert "client_key=tt-key" in url
    assert "tt-secret" not in url
    linkedin = LinkedInAdapter(env={"LINKEDIN_CLIENT_ID": "li-id", "LINKEDIN_CLIENT_SECRET": "li-secret"})
    auth = linkedin.authorization_url("st", "https://app.example/li")
    assert "client_id=li-id" in auth
    assert "w_member_social" in auth
    assert "li-secret" not in auth
    assert get_adapter("youtube").platform == "youtube"


# --- scheduler ---


class _ScriptAdapter:
    def __init__(self):
        self.tokens = []
        self.published = 0

    def refresh(self, account):
        return TokenBundle(access_token="refreshed-token-value", refresh_token="refreshed-refresh", expires_in=3600)

    def publish(self, account, media, caption, options=None):
        self.tokens.append(account.get("access_token"))
        self.published += 1
        return type("R", (), {"remote_id": "remote-1", "permalink": "https://example.com/p/1", "warnings": []})()


class _TransientAdapter:
    def refresh(self, account):
        raise AssertionError("refresh should not run")

    def publish(self, account, media, caption, options=None):
        raise PlatformError("busy", transient=True)


class _LeakAdapter:
    def refresh(self, account):
        raise AssertionError("refresh should not run")

    def publish(self, account, media, caption, options=None):
        raise RuntimeError("blew up " + account["access_token"])


def _queued(store, account_id, when):
    return store.add_post(
        {
            "account_id": account_id,
            "platform": "x",
            "handle": "@luma",
            "creative": {"style_name": "Claymation", "media_kind": "image"},
            "caption": "Hello",
            "scheduled_at": when,
            "status": "queued",
            "dry_run": False,
            "payload": {"privacy": "PUBLIC"},
        }
    )


def test_scheduler_publishes_retries_and_survives_reopen(tmp_path, caplog):
    os.environ["SOCIAL_STUDIO_SECRET_KEY"] = SECRET
    caplog.set_level(logging.ERROR)
    try:
        path = str(tmp_path / "queue.db")
        store = SocialStore(path)
        account = store.upsert_account(
            platform="x",
            handle="@luma",
            display_name="Luma",
            external_id="x-1",
            access_token=TOKEN,
            refresh_token="refresh-secret-value",
            token_expiry="2099-01-01T00:00:00Z",
        )
        now = "2026-11-02T18:00:00Z"
        post = _queued(store, account["id"], now)
        adapter = _ScriptAdapter()
        done = execute_post(store, post, adapters={"x": adapter}, now=now)
        assert done["status"] == "posted"
        assert done["permalink"] == "https://example.com/p/1"
        assert adapter.tokens == [TOKEN]
        reopened = SocialStore(path)
        assert reopened.get_post(post["id"])["status"] == "posted"

        expired = store.upsert_account(
            platform="facebook",
            handle="Page",
            display_name="Page",
            external_id="page-1",
            access_token="old-token-value",
            refresh_token="old-refresh-value",
            token_expiry="2020-01-01T00:00:00Z",
        )
        due = store.add_post(
            {
                "account_id": expired["id"],
                "platform": "facebook",
                "handle": "Page",
                "creative": {},
                "caption": "Hi",
                "scheduled_at": now,
                "status": "queued",
                "payload": {"privacy": "PUBLISHED"},
            }
        )
        facebook = _ScriptAdapter()
        execute_post(store, due, adapters={"facebook": facebook}, now=now)
        assert facebook.tokens == ["refreshed-token-value"]
        assert (
            store.get_account(expired["id"], include_secrets=True)["access_token"]
            == "refreshed-token-value"
        )

        retry_account = account
        retry = _queued(store, retry_account["id"], now)
        transient = _TransientAdapter()
        first = execute_post(store, retry, adapters={"x": transient}, now=now)
        assert first["status"] == "queued"
        assert first["attempts"] == 1
        assert first["next_attempt_at"] == shift(now, 30)
        assert tick(store, adapters={"x": transient}, now=now) == []
        assert store.get_post(retry["id"])["attempts"] == 1
        second = execute_post(
            store,
            store.get_post(retry["id"]),
            adapters={"x": transient},
            now=first["next_attempt_at"],
        )
        assert second["attempts"] == 2
        assert second["status"] == "queued"

        leak = _queued(store, account["id"], now)
        logged = execute_post(store, leak, adapters={"x": _LeakAdapter()}, now=now)
        assert TOKEN not in logged["error"]
        assert "[redacted]" in logged["error"]
        assert TOKEN not in caplog.text
    finally:
        os.environ.pop("SOCIAL_STUDIO_SECRET_KEY", None)


def test_scheduler_rate_limit_postpones_without_publishing(tmp_path):
    os.environ["SOCIAL_STUDIO_SECRET_KEY"] = SECRET
    try:
        store = SocialStore(str(tmp_path / "rate.db"))
        account = store.upsert_account(
            platform="x",
            handle="@luma",
            display_name="Luma",
            external_id="x-2",
            access_token=TOKEN,
            token_expiry="2099-01-01T00:00:00Z",
        )
        now = "2026-11-02T18:00:00Z"
        for _ in range(15):
            store.record_rate("x", now)
        post = _queued(store, account["id"], now)
        adapter = _ScriptAdapter()
        updated = execute_post(store, post, adapters={"x": adapter}, now=now)
        assert adapter.published == 0
        assert updated["status"] == "queued"
        assert "Rate limit" in updated["error"]
        assert updated["next_attempt_at"] > now
    finally:
        os.environ.pop("SOCIAL_STUDIO_SECRET_KEY", None)


# --- nodes and routes ---


def test_nodes_dry_run_does_not_publish_and_hides_tokens(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIAL_STUDIO_SECRET_KEY", SECRET)
    monkeypatch.setenv("SOCIAL_STUDIO_DATABASE", str(tmp_path / "nodes.db"))
    store = get_store()
    store.upsert_account(
        platform="tiktok",
        handle="@luma",
        display_name="Luma",
        external_id="tt-1",
        tags=["luma"],
        access_token=TOKEN,
        token_expiry="2099-01-01T00:00:00Z",
        extra={"tiktok_audited": False},
    )
    store.upsert_account(
        platform="x",
        handle="@luma",
        display_name="Luma X",
        external_id="x-9",
        tags=["luma"],
        access_token=TOKEN,
        token_expiry="2099-01-01T00:00:00Z",
    )
    select = SocialAccountSelect()
    selected = select.evaluate(_inputs(optional={"mode": "tag", "tag": "luma"}))
    assert selected["count"] == 2
    assert TOKEN not in json.dumps(selected)
    creatives = [
        dict(_creative(0), favorite=True),
        dict(_creative(1), discarded=True),
    ]
    captions_node = SocialCaptionVariations()
    pack = captions_node.evaluate(
        _inputs(
            required={"creative": creatives},
            optional={"count": "2", "use_model": "no", "include": "all_kept"},
        )
    )
    assert len(pack["creatives"]) == 1
    assert pack["model"] == "heuristic"
    called = {"tick": 0}

    def _no_tick(*args, **kwargs):
        called["tick"] += 1
        return []

    monkeypatch.setattr("custom_extensions.social_studio.extension.tick", _no_tick)
    distribute = SocialDistribute()
    plan = distribute.evaluate(
        _inputs(
            required={"creatives": pack, "accounts": selected},
            optional={
                "strategy": "round-robin",
                "dry_run": "yes",
                "schedule_at": "2026-11-02T18:00:00Z",
                "stagger_seconds": "0",
                "jitter_seconds": "0",
            },
        )
    )
    assert called["tick"] == 0
    assert plan["dry_run"] is True
    assert plan["items"][0]["status"] == "dry_run"
    assert TOKEN not in json.dumps(plan)
    log = SocialPostLog().evaluate(_inputs(optional={"plan": plan, "limit": "10"}))
    assert log["posts"]
    assert TOKEN not in json.dumps(log)


def test_example_workflow_wires_ad_studio_into_a_dry_run():
    graph = build_workflow()
    types = [node["type"] for node in graph["nodes"]]
    assert "ad_studio/AdCreative" in types
    assert "ad_studio/AdFrame916" in types
    assert "social_studio/SocialCaptionVariations" in types
    assert "social_studio/SocialDistribute" in types
    distribute = next(node for node in graph["nodes"] if node["type"] == "social_studio/SocialDistribute")
    assert distribute["widgets_values"][1] == "yes"
    discarded = [
        node
        for node in graph["nodes"]
        if node["type"] == "ad_studio/AdCreative" and node["mode"] == 2
    ]
    assert discarded
    assert example_workflow_path().endswith("social_studio_dry_run.json")


def _app(server):
    from custom_extensions.social_studio.routes import register_routes

    register_routes(server)
    server.app.add_routes(server.routes)
    return server.app


def test_routes_accounts_plan_and_oauth_callback(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIAL_STUDIO_SECRET_KEY", SECRET)
    monkeypatch.setenv("SOCIAL_STUDIO_DATABASE", str(tmp_path / "http.db"))
    monkeypatch.delenv("TIKTOK_CLIENT_KEY", raising=False)
    monkeypatch.delenv("TIKTOK_CLIENT_SECRET", raising=False)

    class Stub:
        routes = web.RouteTableDef()
        app = web.Application()
        extensions = {"social_studio": {"javascript": "DRY RUN social_studio/SocialDistribute"}}
        output_directory = str(tmp_path)
        logger = logging.getLogger("social-studio-test")

    stub = Stub()

    async def scenario():
        client = TestClient(TestServer(_app(stub)))
        await client.start_server()
        try:
            panel = await client.get("/social-studio/accounts?demo=1")
            assert panel.status == 200
            html = await panel.text()
            assert "PLACEHOLDER" in html
            assert "SELF_ONLY" in html
            assert "@luma.labs" in html

            plan = await client.get("/social-studio/plan?demo=1")
            plan_html = await plan.text()
            assert "DRY RUN" in plan_html
            assert "PLACEHOLDER" in plan_html
            assert "Claymation" in plan_html

            created = await client.post(
                "/social-studio/accounts",
                json={
                    "platform": "x",
                    "handle": "@luma",
                    "display_name": "Luma",
                    "tags": ["luma"],
                    "access_token": TOKEN,
                    "refresh_token": "refresh-secret-value",
                    "expires_in": 3600,
                },
            )
            assert created.status == 200
            body = await created.json()
            assert TOKEN not in json.dumps(body)
            account_id = body["account"]["id"]
            listed = await client.get("/social-studio/accounts.json")
            listed_body = await listed.text()
            assert TOKEN not in listed_body
            assert "@luma" in listed_body
            raw = (tmp_path / "http.db").read_bytes()
            assert TOKEN.encode() not in raw

            tagged = await client.post(
                f"/social-studio/accounts/{account_id}/tag",
                json={"tag": "launch"},
            )
            assert "launch" in json.dumps(await tagged.json())
            grouped = await client.post(
                "/social-studio/groups",
                json={"ids": [account_id], "tag": "batch"},
            )
            assert "batch" in json.dumps(await grouped.json())

            connect = await client.get("/social-studio/connect/tiktok")
            assert connect.status == 400
            text = await connect.text()
            assert "TIKTOK_CLIENT_KEY" in text

            from custom_extensions.social_studio.platforms.base import ConnectedAccount
            from custom_extensions.social_studio.routes import get_store as route_store

            class FakeOAuth:
                def exchange_code(self, code, redirect_uri, code_verifier=""):
                    assert code == "auth-code"
                    assert code_verifier
                    return TokenBundle(
                        access_token=TOKEN,
                        refresh_token="refresh-secret-value",
                        expires_in=1200,
                        scopes=["tweet.write"],
                    )

                def fetch_accounts(self, bundle):
                    return [
                        ConnectedAccount(
                            platform="x",
                            handle="@from-oauth",
                            display_name="OAuth Luma",
                            external_id="oauth-user",
                            access_token=bundle.access_token,
                            refresh_token=bundle.refresh_token,
                            expires_in=bundle.expires_in,
                            scopes=bundle.scopes,
                            extra={},
                        )
                    ]

            monkeypatch.setattr(
                "custom_extensions.social_studio.routes.get_adapter",
                lambda platform: FakeOAuth(),
            )
            route_store(stub).save_oauth_state(
                state="state-1",
                platform="x",
                code_verifier="verifier-1",
                redirect_uri="https://app.example/callback",
            )
            callback = await client.get(
                "/social-studio/oauth/x/callback",
                params={"code": "auth-code", "state": "state-1"},
                allow_redirects=False,
            )
            assert callback.status in (302, 303)
            assert "access_token" not in callback.headers.get("Location", "")
            rows = route_store(stub).list_accounts()
            assert any(row["handle"] == "@from-oauth" for row in rows)
            secret = route_store(stub).get_account(
                next(row["id"] for row in rows if row["handle"] == "@from-oauth"),
                include_secrets=True,
            )
            assert secret["access_token"] == TOKEN
            assert TOKEN.encode() not in (tmp_path / "http.db").read_bytes()

            removed = await client.delete(
                f"/social-studio/accounts/{account_id}",
                headers={"Accept": "application/json"},
            )
            assert (await removed.json())["removed"] == account_id
            assert pages.placeholder_accounts()[0]["status"] == "placeholder"
            assert expiry_from_seconds(10)
        finally:
            await client.close()

    import asyncio

    asyncio.run(scenario())
