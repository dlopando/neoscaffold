"""Facebook Pages via the Graph API.

Connect lists every Page the user can manage and stores that Page's
access token. Photos and videos are uploaded as multipart bytes.
"""

from . import meta
from .base import (
    ConnectedAccount,
    MediaSource,
    PlatformAdapter,
    PlatformError,
    PublishResult,
    read_file,
)


class FacebookAdapter(PlatformAdapter):
    platform = "facebook"
    label = "Facebook Page"
    scopes = (
        "pages_show_list",
        "pages_read_engagement",
        "pages_manage_posts",
        "public_profile",
    )
    docs_url = "https://developers.facebook.com/docs/pages-api/posts"
    audit_notes = (
        "Meta app review is required for pages_manage_posts if anyone other than an app role will connect.",
        "Posts are published as the Page, using the Page access token from /me/accounts.",
    )
    implements = (
        "oauth via Facebook Login",
        "one stored account per Page",
        "photo upload (multipart)",
        "video upload (multipart)",
        "permalink lookup",
    )
    not_implemented = (
        "Reels-specific Facebook publishing.",
        "Stories.",
    )
    env_vars = (
        "FACEBOOK_APP_ID",
        "FACEBOOK_APP_SECRET",
        "FACEBOOK_REDIRECT_URI",
        "META_APP_ID",
        "META_APP_SECRET",
        "META_GRAPH_VERSION",
    )
    client_id_env = "FACEBOOK_APP_ID"
    client_secret_env = "FACEBOOK_APP_SECRET"

    def setting(self, name, default=""):
        value = super().setting(name, "")
        if value:
            return value
        if name == "FACEBOOK_APP_ID":
            return super().setting("META_APP_ID", default)
        if name == "FACEBOOK_APP_SECRET":
            return super().setting("META_APP_SECRET", default)
        return default

    def missing_settings(self):
        missing = []
        if not self.setting("FACEBOOK_APP_ID"):
            missing.append("FACEBOOK_APP_ID or META_APP_ID")
        if not self.setting("FACEBOOK_APP_SECRET"):
            missing.append("FACEBOOK_APP_SECRET or META_APP_SECRET")
        return missing

    def authorization_url(self, state, redirect_uri, code_challenge=""):
        return meta.dialog_url(self, redirect_uri, state, self.scopes)

    def exchange_code(self, code, redirect_uri, code_verifier=""):
        return meta.exchange_code(self, code, redirect_uri)

    def refresh(self, account):
        return meta.refresh_long_lived(self, account)

    def fetch_accounts(self, bundle):
        pages = meta.list_pages(self, bundle.access_token)
        accounts = []
        for page in pages:
            if not page.get("id") or not page.get("access_token"):
                continue
            name = page.get("name") or "Facebook Page"
            username = page.get("username") or ""
            handle = "@" + username if username else name
            accounts.append(
                ConnectedAccount(
                    platform=self.platform,
                    handle=handle,
                    display_name=name,
                    external_id=str(page.get("id")),
                    access_token=page.get("access_token"),
                    refresh_token=bundle.access_token,
                    expires_in=bundle.expires_in,
                    scopes=list(bundle.scopes or self.scopes),
                    extra={"page_id": str(page.get("id")), "token_role": "page"},
                )
            )
        if not accounts:
            raise PlatformError("This Facebook user does not manage any Pages.")
        return accounts

    def upload_media(self, account, media):
        return _coerce(media)

    def publish(self, account, media, caption, options=None):
        options = options or {}
        media = self.upload_media(account, media)
        page_id = (account.get("extra") or {}).get("page_id") or account.get("external_id")
        if not page_id:
            raise PlatformError("Facebook account is missing page_id. Reconnect the Page.")
        token = account.get("access_token") or ""
        published = "false" if options.get("privacy") == "UNPUBLISHED" else "true"
        if media.kind == "video":
            endpoint = "videos"
            filename = media.filename or "video.mp4"
            mime = media.mime or "video/mp4"
        else:
            endpoint = "photos"
            filename = media.filename or "image.jpg"
            mime = media.mime or "image/jpeg"
        content = read_file(media.path) if media.path else b""
        if not content and media.url:
            raise PlatformError(
                "Facebook upload is implemented for local files. "
                "This creative has a URL but no local path."
            )
        if not content:
            raise PlatformError("Facebook publish needs a local media file.")
        response = self.transport.request(
            "POST",
            f"{meta.GRAPH}/{meta.graph_version(self)}/{page_id}/{endpoint}",
            data={"caption": caption or "", "published": published},
            files={"source": (filename, content, mime)},
            headers={"Authorization": "Bearer " + token},
        )
        response.raise_for_status()
        body = response.json()
        remote_id = str(body.get("post_id") or body.get("id") or "")
        if not remote_id:
            raise PlatformError("Facebook did not return a post id")
        return PublishResult(remote_id=remote_id, permalink="", raw={"id": remote_id})

    def get_status(self, account, remote_id):
        payload = meta.graph_get(
            self,
            remote_id,
            account.get("access_token") or "",
            {"fields": "id,permalink_url,created_time"},
        )
        return {
            "remote_id": remote_id,
            "status": "published" if payload.get("id") else "",
            "permalink": payload.get("permalink_url") or "",
            "raw": payload,
        }


def _coerce(media):
    if isinstance(media, MediaSource):
        return media
    return MediaSource(**{key: media[key] for key in media if key in MediaSource.__dataclass_fields__})
