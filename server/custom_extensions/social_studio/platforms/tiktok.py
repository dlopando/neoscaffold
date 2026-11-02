"""TikTok Content Posting API (Direct Post).

Unaudited apps may only send privacy_level SELF_ONLY. Public posting
requires a passed TikTok audit and TIKTOK_CONTENT_POSTING_AUDITED=true.
Photo posts pull from a public HTTPS URL. Video posts upload bytes.
"""

import os

from .base import (
    ConnectedAccount,
    MediaSource,
    PlatformAdapter,
    PlatformError,
    PublishResult,
    bearer,
    bundle_from_payload,
    oauth_error,
    read_file,
)

_AUTH = "https://www.tiktok.com/v2/auth/authorize/"
_TOKEN = "https://open.tiktokapis.com/v2/oauth/token/"
_USER = "https://open.tiktokapis.com/v2/user/info/"
_PHOTO = "https://open.tiktokapis.com/v2/post/publish/content/init/"
_VIDEO = "https://open.tiktokapis.com/v2/post/publish/video/init/"
_STATUS = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"


class TikTokAdapter(PlatformAdapter):
    platform = "tiktok"
    label = "TikTok"
    scopes = ("user.info.basic", "user.info.profile", "video.publish", "video.upload")
    docs_url = "https://developers.tiktok.com/doc/content-posting-api-get-started"
    audit_notes = (
        "Unaudited apps can only post with privacy_level SELF_ONLY (private).",
        "Public direct posts require a TikTok app audit, then TIKTOK_CONTENT_POSTING_AUDITED=true.",
        "Photo direct post pulls from a public HTTPS URL (PULL_FROM_URL).",
    )
    implements = (
        "oauth",
        "refresh",
        "photo direct post via public URL",
        "video direct post via file upload",
        "publish status",
    )
    not_implemented = (
        "Photo byte upload. TikTok photo direct post is PULL_FROM_URL only.",
    )
    env_vars = (
        "TIKTOK_CLIENT_KEY",
        "TIKTOK_CLIENT_SECRET",
        "TIKTOK_REDIRECT_URI",
        "TIKTOK_CONTENT_POSTING_AUDITED",
    )

    def audited(self):
        return self.setting("TIKTOK_CONTENT_POSTING_AUDITED").lower() in (
            "1",
            "true",
            "yes",
        )

    def authorization_url(self, state, redirect_uri, code_challenge=""):
        from urllib.parse import urlencode

        query = urlencode(
            {
                "client_key": self.setting("TIKTOK_CLIENT_KEY"),
                "response_type": "code",
                "scope": ",".join(self.scopes),
                "redirect_uri": redirect_uri,
                "state": state,
            }
        )
        return _AUTH + "?" + query

    def exchange_code(self, code, redirect_uri, code_verifier=""):
        response = self.transport.request(
            "POST",
            _TOKEN,
            data={
                "client_key": self.setting("TIKTOK_CLIENT_KEY"),
                "client_secret": self.setting("TIKTOK_CLIENT_SECRET"),
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
        )
        response.raise_for_status()
        return bundle_from_payload(response.json())

    def refresh(self, account):
        response = self.transport.request(
            "POST",
            _TOKEN,
            data={
                "client_key": self.setting("TIKTOK_CLIENT_KEY"),
                "client_secret": self.setting("TIKTOK_CLIENT_SECRET"),
                "grant_type": "refresh_token",
                "refresh_token": account.get("refresh_token") or "",
            },
        )
        response.raise_for_status()
        return bundle_from_payload(response.json())

    def fetch_accounts(self, bundle):
        response = self.transport.request(
            "GET",
            _USER,
            params={"fields": "open_id,display_name,username,avatar_url"},
            headers=bearer(bundle.access_token),
        )
        response.raise_for_status()
        payload = response.json()
        message = oauth_error(payload)
        if message:
            raise PlatformError("TikTok user info failed: " + message)
        user = (payload.get("data") or {}).get("user") or {}
        username = user.get("username") or user.get("open_id") or "tiktok"
        handle = username if str(username).startswith("@") else "@" + str(username)
        return [
            ConnectedAccount(
                platform=self.platform,
                handle=handle,
                display_name=user.get("display_name") or handle,
                external_id=str(user.get("open_id") or username),
                access_token=bundle.access_token,
                refresh_token=bundle.refresh_token,
                expires_in=bundle.expires_in,
                scopes=list(bundle.scopes or self.scopes),
                extra={
                    "tiktok_audited": self.audited(),
                    "privacy_note": (
                        "Audit approved: public direct post is allowed."
                        if self.audited()
                        else "Unaudited app: posts are forced to SELF_ONLY (private)."
                    ),
                },
            )
        ]

    def upload_media(self, account, media):
        media = _coerce_media(media)
        if media.kind == "video":
            return media
        url = _public_image_url(media)
        if not url:
            raise PlatformError(
                "TikTok photo direct post requires a public HTTPS image URL. "
                "Set SOCIAL_STUDIO_PUBLIC_MEDIA_BASE or image_url. "
                "Byte upload for photos is not part of the Content Posting photo API."
            )
        media.url = url
        return media

    def publish(self, account, media, caption, options=None):
        options = options or {}
        media = self.upload_media(account, media)
        privacy = options.get("privacy") or "SELF_ONLY"
        if not self.audited():
            privacy = "SELF_ONLY"
        token = account.get("access_token") or ""
        if media.kind == "video":
            return self._publish_video(token, media, caption, privacy)
        body = {
            "media_type": "PHOTO",
            "post_mode": "DIRECT_POST",
            "post_info": {
                "title": _title(caption),
                "description": caption or "",
                "privacy_level": privacy,
                "disable_comment": False,
                "auto_add_music": True,
                "brand_content_toggle": False,
                "brand_organic_toggle": False,
            },
            "source_info": {
                "source": "PULL_FROM_URL",
                "photo_cover_index": 0,
                "photo_images": [media.url],
            },
        }
        response = self.transport.request(
            "POST", _PHOTO, json_body=body, headers=bearer(token)
        )
        response.raise_for_status()
        return _publish_result(response.json(), privacy, self.audited())

    def _publish_video(self, token, media, caption, privacy):
        data = read_file(media.path)
        chunk = len(data) or 1
        body = {
            "post_info": {
                "title": _title(caption),
                "privacy_level": privacy,
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
                "video_cover_timestamp_ms": 1000,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": len(data),
                "chunk_size": chunk,
                "total_chunk_count": 1,
            },
        }
        response = self.transport.request(
            "POST", _VIDEO, json_body=body, headers=bearer(token)
        )
        response.raise_for_status()
        payload = response.json()
        message = oauth_error(payload)
        if message:
            raise PlatformError("TikTok video init failed: " + message)
        upload_url = ((payload.get("data") or {}).get("upload_url")) or ""
        publish_id = ((payload.get("data") or {}).get("publish_id")) or ""
        if not upload_url or not publish_id:
            raise PlatformError("TikTok video init did not return upload_url and publish_id")
        upload = self.transport.request(
            "PUT",
            upload_url,
            raw=data,
            headers={
                "Content-Type": media.mime or "video/mp4",
                "Content-Length": str(len(data)),
                "Content-Range": f"bytes 0-{len(data) - 1}/{len(data)}",
            },
        )
        upload.raise_for_status()
        result = _publish_result(payload, privacy, self.audited())
        result.remote_id = publish_id
        return result

    def get_status(self, account, remote_id):
        response = self.transport.request(
            "POST",
            _STATUS,
            json_body={"publish_id": remote_id},
            headers=bearer(account.get("access_token") or ""),
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") or {}
        return {
            "remote_id": remote_id,
            "status": data.get("status") or "",
            "permalink": "",
            "raw": data,
        }


def _publish_result(payload, privacy, audited):
    message = oauth_error(payload)
    if message:
        raise PlatformError("TikTok publish failed: " + message)
    data = payload.get("data") or {}
    warnings = []
    if privacy == "SELF_ONLY" and not audited:
        warnings.append("Posted as SELF_ONLY because the TikTok app is not marked audited.")
    return PublishResult(
        remote_id=str(data.get("publish_id") or ""),
        permalink="",
        raw={"publish_id": data.get("publish_id"), "privacy_level": privacy},
        warnings=warnings,
    )


def _title(caption):
    text = str(caption or "").strip().split("\n", 1)[0]
    return text[:150]


def _coerce_media(media):
    if isinstance(media, MediaSource):
        return media
    return MediaSource(**{key: media.get(key) for key in MediaSource.__dataclass_fields__ if key in media})


def _public_image_url(media):
    url = str(media.url or "")
    if url.startswith("https://"):
        return url
    base = os.environ.get("SOCIAL_STUDIO_PUBLIC_MEDIA_BASE", "").rstrip("/")
    if base and media.filename:
        return base + "/social-studio/media/" + media.filename
    return ""
