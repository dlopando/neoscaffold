"""YouTube Data API uploads.

``videos.insert`` publishes a video. Shorts are vertical uploads; this
adapter adds #Shorts to the description when it is missing. The public
Data API does not publish still images or community posts, so image
creatives raise NotImplementedError.
"""

from urllib.parse import urlencode

from .base import (
    ConnectedAccount,
    MediaSource,
    PlatformAdapter,
    PlatformError,
    PlatformNotImplemented,
    PublishResult,
    bearer,
    bundle_from_payload,
    read_file,
)

_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN = "https://oauth2.googleapis.com/token"
_CHANNELS = "https://www.googleapis.com/youtube/v3/channels"
_INSERT = "https://www.googleapis.com/upload/youtube/v3/videos"
_VIDEOS = "https://www.googleapis.com/youtube/v3/videos"
_SCOPES = (
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
)


class YouTubeAdapter(PlatformAdapter):
    platform = "youtube"
    label = "YouTube"
    scopes = _SCOPES
    docs_url = "https://developers.google.com/youtube/v3/docs/videos/insert"
    audit_notes = (
        "YouTube Data API quota defaults to 10,000 units per day. videos.insert costs about 1,600 units, so a default project can upload about six videos a day.",
        "youtube.upload is a sensitive scope. External users need a verified OAuth consent screen.",
        "Still images are not supported. Community posts are not in the public Data API.",
    )
    implements = (
        "oauth with PKCE and offline refresh",
        "resumable video upload",
        "Shorts description tag",
        "video status lookup",
    )
    not_implemented = (
        "Still-image posts and community posts. YouTube Data API publishes videos only.",
    )
    env_vars = ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REDIRECT_URI")

    def authorization_url(self, state, redirect_uri, code_challenge=""):
        if not code_challenge:
            raise PlatformError("YouTube OAuth requires a PKCE code_challenge")
        query = urlencode(
            {
                "client_id": self.setting("YOUTUBE_CLIENT_ID"),
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": " ".join(self.scopes),
                "access_type": "offline",
                "prompt": "consent",
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
        )
        return _AUTH + "?" + query

    def exchange_code(self, code, redirect_uri, code_verifier=""):
        response = self.transport.request(
            "POST",
            _TOKEN,
            data={
                "code": code,
                "client_id": self.setting("YOUTUBE_CLIENT_ID"),
                "client_secret": self.setting("YOUTUBE_CLIENT_SECRET"),
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            },
        )
        response.raise_for_status()
        return bundle_from_payload(response.json())

    def refresh(self, account):
        response = self.transport.request(
            "POST",
            _TOKEN,
            data={
                "client_id": self.setting("YOUTUBE_CLIENT_ID"),
                "client_secret": self.setting("YOUTUBE_CLIENT_SECRET"),
                "refresh_token": account.get("refresh_token") or "",
                "grant_type": "refresh_token",
            },
        )
        response.raise_for_status()
        bundle = bundle_from_payload(response.json())
        if not bundle.refresh_token:
            bundle.refresh_token = account.get("refresh_token") or ""
        return bundle

    def fetch_accounts(self, bundle):
        response = self.transport.request(
            "GET",
            _CHANNELS,
            params={"part": "snippet", "mine": "true"},
            headers=bearer(bundle.access_token),
        )
        response.raise_for_status()
        items = response.json().get("items") or []
        if not items:
            raise PlatformError("This Google account has no YouTube channel.")
        channel = items[0]
        snippet = channel.get("snippet") or {}
        custom = snippet.get("customUrl") or channel.get("id")
        handle = custom if str(custom).startswith("@") else "@" + str(custom)
        return [
            ConnectedAccount(
                platform=self.platform,
                handle=handle,
                display_name=snippet.get("title") or handle,
                external_id=str(channel.get("id") or ""),
                access_token=bundle.access_token,
                refresh_token=bundle.refresh_token,
                expires_in=bundle.expires_in,
                scopes=list(bundle.scopes or self.scopes),
                extra={"channel_id": str(channel.get("id") or "")},
            )
        ]

    def upload_media(self, account, media):
        media = _coerce(media)
        if media.kind != "video":
            raise PlatformNotImplemented(
                "YouTube Data API does not publish still images. "
                "Community posts are not available on the public videos.insert API. "
                "Pass a video file to upload a Short."
            )
        return media

    def publish(self, account, media, caption, options=None):
        options = options or {}
        media = self.upload_media(account, media)
        data = read_file(media.path)
        description = caption or ""
        if "#shorts" not in description.lower():
            description = (description + "\n#Shorts").strip()
        title = _title(caption)
        privacy = options.get("privacy") or "public"
        if privacy not in ("public", "private", "unlisted"):
            privacy = "public"
        meta_body = {
            "snippet": {
                "title": title,
                "description": description,
                "categoryId": "22",
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
            },
        }
        start = self.transport.request(
            "POST",
            _INSERT,
            params={"uploadType": "resumable", "part": "snippet,status"},
            json_body=meta_body,
            headers={
                **bearer(account.get("access_token") or ""),
                "X-Upload-Content-Type": media.mime or "video/mp4",
                "X-Upload-Content-Length": str(len(data)),
            },
        )
        start.raise_for_status()
        location = start.headers.get("location") or ""
        if not location:
            raise PlatformError("YouTube resumable upload did not return a Location header")
        uploaded = self.transport.request(
            "PUT",
            location,
            raw=data,
            headers={
                "Content-Type": media.mime or "video/mp4",
                "Content-Length": str(len(data)),
            },
        )
        uploaded.raise_for_status()
        body = uploaded.json()
        remote_id = str(body.get("id") or "")
        if not remote_id:
            raise PlatformError("YouTube did not return a video id")
        return PublishResult(
            remote_id=remote_id,
            permalink="https://www.youtube.com/shorts/" + remote_id,
            raw={"id": remote_id, "privacyStatus": privacy},
        )

    def get_status(self, account, remote_id):
        response = self.transport.request(
            "GET",
            _VIDEOS,
            params={"part": "status,snippet", "id": remote_id},
            headers=bearer(account.get("access_token") or ""),
        )
        response.raise_for_status()
        items = response.json().get("items") or []
        status = ""
        if items:
            status = ((items[0].get("status") or {}).get("uploadStatus")) or ""
        return {
            "remote_id": remote_id,
            "status": status,
            "permalink": "https://www.youtube.com/shorts/" + str(remote_id),
            "raw": items[0] if items else {},
        }


def _title(caption):
    line = str(caption or "Short").strip().split("\n", 1)[0]
    line = line.replace("#Shorts", "").replace("#shorts", "").strip() or "Short"
    return line[:100]


def _coerce(media):
    if isinstance(media, MediaSource):
        return media
    return MediaSource(**{key: media[key] for key in media if key in MediaSource.__dataclass_fields__})
