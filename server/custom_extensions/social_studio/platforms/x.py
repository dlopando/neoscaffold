"""X API v2 with OAuth 2.0 PKCE.

Media is uploaded with POST /2/media/upload, then the post is created
with POST /2/tweets. Write limits depend on the app's X API tier.
"""

import base64
import hashlib
from urllib.parse import urlencode

from .base import (
    ConnectedAccount,
    MediaSource,
    PlatformAdapter,
    PlatformError,
    PublishResult,
    bearer,
    bundle_from_payload,
    read_file,
)

_AUTH = "https://twitter.com/i/oauth2/authorize"
_TOKEN = "https://api.x.com/2/oauth2/token"
_ME = "https://api.x.com/2/users/me"
_MEDIA = "https://api.x.com/2/media/upload"
_TWEETS = "https://api.x.com/2/tweets"


class XAdapter(PlatformAdapter):
    platform = "x"
    label = "X"
    scopes = ("tweet.read", "tweet.write", "users.read", "offline.access", "media.write")
    docs_url = "https://docs.x.com/x-api/posts/creation-of-a-post"
    audit_notes = (
        "OAuth 2.0 PKCE is required. Put the redirect URI on the app in the X developer portal.",
        "Free, Basic, and Pro tiers have different monthly write caps. A 403 from /2/tweets is usually the tier, not this adapter.",
        "media.write must be enabled on the app or upload returns 403.",
    )
    implements = (
        "oauth 2.0 PKCE",
        "refresh",
        "image upload + create post",
        "video upload + create post",
        "post lookup",
    )
    not_implemented = (
        "Chunked upload for very large videos. This adapter sends the file in one /2/media/upload call.",
        "Polls, threads, and long-form articles.",
    )
    env_vars = ("X_CLIENT_ID", "X_CLIENT_SECRET", "X_REDIRECT_URI")

    def authorization_url(self, state, redirect_uri, code_challenge=""):
        if not code_challenge:
            raise PlatformError("X OAuth requires a PKCE code_challenge")
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self.setting("X_CLIENT_ID"),
                "redirect_uri": redirect_uri,
                "scope": " ".join(self.scopes),
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
        )
        return _AUTH + "?" + query

    def exchange_code(self, code, redirect_uri, code_verifier=""):
        if not code_verifier:
            raise PlatformError("X token exchange requires the PKCE code_verifier")
        response = self.transport.request(
            "POST",
            _TOKEN,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
                "client_id": self.setting("X_CLIENT_ID"),
            },
            headers=self._basic_headers(),
        )
        response.raise_for_status()
        return bundle_from_payload(response.json())

    def refresh(self, account):
        response = self.transport.request(
            "POST",
            _TOKEN,
            data={
                "grant_type": "refresh_token",
                "refresh_token": account.get("refresh_token") or "",
                "client_id": self.setting("X_CLIENT_ID"),
            },
            headers=self._basic_headers(),
        )
        response.raise_for_status()
        bundle = bundle_from_payload(response.json())
        if not bundle.refresh_token:
            bundle.refresh_token = account.get("refresh_token") or ""
        return bundle

    def fetch_accounts(self, bundle):
        response = self.transport.request(
            "GET",
            _ME,
            params={"user.fields": "username,name"},
            headers=bearer(bundle.access_token),
        )
        response.raise_for_status()
        user = (response.json().get("data") or {})
        username = user.get("username") or user.get("id") or "x"
        handle = "@" + str(username)
        return [
            ConnectedAccount(
                platform=self.platform,
                handle=handle,
                display_name=user.get("name") or handle,
                external_id=str(user.get("id") or username),
                access_token=bundle.access_token,
                refresh_token=bundle.refresh_token,
                expires_in=bundle.expires_in,
                scopes=list(bundle.scopes or self.scopes),
                extra={},
            )
        ]

    def upload_media(self, account, media):
        media = _coerce(media)
        content = read_file(media.path)
        category = "tweet_video" if media.kind == "video" else "tweet_image"
        mime = media.mime or ("video/mp4" if media.kind == "video" else "image/jpeg")
        filename = media.filename or ("video.mp4" if media.kind == "video" else "image.jpg")
        response = self.transport.request(
            "POST",
            _MEDIA,
            data={"media_category": category},
            files={"media": (filename, content, mime)},
            headers=bearer(account.get("access_token") or ""),
        )
        response.raise_for_status()
        body = response.json()
        data = body.get("data") or body
        media_id = str(data.get("id") or data.get("media_id") or "")
        if not media_id:
            raise PlatformError("X media upload did not return a media id")
        media.extra_id = media_id
        return media

    def publish(self, account, media, caption, options=None):
        media = self.upload_media(account, media)
        media_id = getattr(media, "extra_id", "") or ""
        response = self.transport.request(
            "POST",
            _TWEETS,
            json_body={"text": caption or "", "media": {"media_ids": [media_id]}},
            headers=bearer(account.get("access_token") or ""),
        )
        response.raise_for_status()
        data = (response.json().get("data") or {})
        remote_id = str(data.get("id") or "")
        if not remote_id:
            raise PlatformError("X did not return a post id")
        username = str(account.get("handle") or "").lstrip("@")
        permalink = f"https://x.com/{username}/status/{remote_id}" if username else ""
        return PublishResult(remote_id=remote_id, permalink=permalink, raw={"id": remote_id})

    def get_status(self, account, remote_id):
        response = self.transport.request(
            "GET",
            _TWEETS + "/" + str(remote_id),
            headers=bearer(account.get("access_token") or ""),
        )
        response.raise_for_status()
        data = (response.json().get("data") or {})
        return {
            "remote_id": remote_id,
            "status": "posted" if data.get("id") else "",
            "permalink": "",
            "raw": data,
        }

    def _basic_headers(self):
        secret = self.setting("X_CLIENT_SECRET")
        client_id = self.setting("X_CLIENT_ID")
        if not secret:
            return {}
        token = base64.b64encode(f"{client_id}:{secret}".encode("utf-8")).decode("ascii")
        return {"Authorization": "Basic " + token}


def pkce_challenge(verifier):
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _coerce(media):
    if isinstance(media, MediaSource):
        return media
    return MediaSource(**{key: media[key] for key in media if key in MediaSource.__dataclass_fields__})
