"""Instagram Graph API content publishing for professional accounts.

Image and reel posts use the container flow: create a media container
with a public HTTPS URL, then call media_publish. A personal Instagram
account cannot use this API.
"""

from .base import ConnectedAccount, MediaSource, PlatformAdapter, PlatformError, PublishResult
from . import meta


class InstagramAdapter(PlatformAdapter):
    platform = "instagram"
    label = "Instagram"
    scopes = (
        "instagram_basic",
        "instagram_content_publish",
        "pages_show_list",
        "pages_read_engagement",
        "pages_manage_posts",
        "business_management",
    )
    docs_url = "https://developers.facebook.com/docs/instagram-platform/content-publishing"
    audit_notes = (
        "Requires an Instagram professional (business or creator) account linked to a Facebook Page.",
        "Meta app review is required before accounts you do not admin can grant these permissions.",
        "image_url and video_url must be public HTTPS. The API does not accept a raw image upload.",
    )
    implements = (
        "oauth via Facebook Login",
        "long-lived token exchange",
        "image container + media_publish",
        "reel container + media_publish",
        "container status",
    )
    not_implemented = (
        "Carousel posts.",
        "Stories.",
        "Direct byte upload of images. Containers take a public URL.",
    )
    env_vars = (
        "INSTAGRAM_APP_ID",
        "INSTAGRAM_APP_SECRET",
        "INSTAGRAM_REDIRECT_URI",
        "META_APP_ID",
        "META_APP_SECRET",
        "META_GRAPH_VERSION",
    )
    client_id_env = "INSTAGRAM_APP_ID"
    client_secret_env = "INSTAGRAM_APP_SECRET"

    def setting(self, name, default=""):
        value = super().setting(name, "")
        if value:
            return value
        if name == "INSTAGRAM_APP_ID":
            return super().setting("META_APP_ID", default)
        if name == "INSTAGRAM_APP_SECRET":
            return super().setting("META_APP_SECRET", default)
        return default

    def missing_settings(self):
        missing = []
        if not self.setting("INSTAGRAM_APP_ID"):
            missing.append("INSTAGRAM_APP_ID or META_APP_ID")
        if not self.setting("INSTAGRAM_APP_SECRET"):
            missing.append("INSTAGRAM_APP_SECRET or META_APP_SECRET")
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
            ig = page.get("instagram_business_account") or {}
            if not ig.get("id"):
                continue
            username = ig.get("username") or ig.get("id")
            handle = username if str(username).startswith("@") else "@" + str(username)
            accounts.append(
                ConnectedAccount(
                    platform=self.platform,
                    handle=handle,
                    display_name=ig.get("name") or page.get("name") or handle,
                    external_id=str(ig.get("id")),
                    access_token=page.get("access_token") or bundle.access_token,
                    refresh_token=bundle.access_token,
                    expires_in=bundle.expires_in,
                    scopes=list(bundle.scopes or self.scopes),
                    extra={
                        "ig_user_id": str(ig.get("id")),
                        "page_id": str(page.get("id") or ""),
                        "page_name": page.get("name") or "",
                        "token_role": "page",
                    },
                )
            )
        if not accounts:
            raise PlatformError(
                "No Instagram professional account is linked to a Facebook Page this user manages."
            )
        return accounts

    def upload_media(self, account, media):
        media = _coerce(media)
        if media.url.startswith("https://"):
            return media
        raise PlatformError(
            "Instagram Graph publishing needs a public HTTPS image_url or video_url. "
            "Set SOCIAL_STUDIO_PUBLIC_MEDIA_BASE so Social Studio can build one, "
            "or pass image_url. Byte upload is not implemented."
        )

    def publish(self, account, media, caption, options=None):
        media = self.upload_media(account, media)
        ig_user = (account.get("extra") or {}).get("ig_user_id") or account.get("external_id")
        if not ig_user:
            raise PlatformError("Instagram account is missing ig_user_id. Reconnect the account.")
        token = account.get("access_token") or ""
        if media.kind == "video":
            fields = {"media_type": "REELS", "video_url": media.url, "caption": caption or ""}
        else:
            fields = {"image_url": media.url, "caption": caption or ""}
        created = self.transport.request(
            "POST",
            f"{meta.GRAPH}/{meta.graph_version(self)}/{ig_user}/media",
            data=fields,
            headers={"Authorization": "Bearer " + token},
        )
        created.raise_for_status()
        creation = created.json()
        creation_id = str(creation.get("id") or "")
        if not creation_id:
            raise PlatformError("Instagram did not return a media container id")
        published = self.transport.request(
            "POST",
            f"{meta.GRAPH}/{meta.graph_version(self)}/{ig_user}/media_publish",
            data={"creation_id": creation_id},
            headers={"Authorization": "Bearer " + token},
        )
        published.raise_for_status()
        body = published.json()
        remote_id = str(body.get("id") or "")
        if not remote_id:
            raise PlatformError("Instagram media_publish did not return an id")
        return PublishResult(
            remote_id=remote_id,
            permalink="",
            raw={"creation_id": creation_id, "id": remote_id},
        )

    def get_status(self, account, remote_id):
        payload = meta.graph_get(
            self,
            remote_id,
            account.get("access_token") or "",
            {"fields": "id,permalink,status_code,status"},
        )
        return {
            "remote_id": remote_id,
            "status": payload.get("status_code") or payload.get("status") or "",
            "permalink": payload.get("permalink") or "",
            "raw": payload,
        }


def _coerce(media):
    if isinstance(media, MediaSource):
        return media
    return MediaSource(**{key: media[key] for key in media if key in MediaSource.__dataclass_fields__})
