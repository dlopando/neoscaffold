"""LinkedIn Posts API for a member, or an organization when configured.

Images use initializeUpload, a binary PUT, then POST /rest/posts.
Video posts are not implemented: they need the Videos API multi-part
upload, which is a different product flow.
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

_AUTH = "https://www.linkedin.com/oauth/v2/authorization"
_TOKEN = "https://www.linkedin.com/oauth/v2/accessToken"
_USERINFO = "https://api.linkedin.com/v2/userinfo"
_IMAGES = "https://api.linkedin.com/rest/images"
_POSTS = "https://api.linkedin.com/rest/posts"


class LinkedInAdapter(PlatformAdapter):
    platform = "linkedin"
    label = "LinkedIn"
    scopes = ("openid", "profile", "w_member_social")
    docs_url = "https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api"
    audit_notes = (
        "Share on LinkedIn (w_member_social) must be added to the developer app.",
        "Organization posts need the Community Management API product and w_organization_social, which LinkedIn approves separately.",
        "Set LINKEDIN_ORGANIZATION_ID to post as that organization. Leave it empty to post as the member.",
    )
    implements = (
        "oauth",
        "refresh",
        "member image post",
        "organization image post when LINKEDIN_ORGANIZATION_ID or the account extra has an organization id",
    )
    not_implemented = (
        "Video posts. The Videos API initializeUpload plus multi-part upload is not implemented.",
        "Document posts and article reshare.",
    )
    env_vars = (
        "LINKEDIN_CLIENT_ID",
        "LINKEDIN_CLIENT_SECRET",
        "LINKEDIN_REDIRECT_URI",
        "LINKEDIN_ORGANIZATION_ID",
        "LINKEDIN_API_VERSION",
    )

    def authorization_url(self, state, redirect_uri, code_challenge=""):
        scopes = list(self.scopes)
        if self.setting("LINKEDIN_ORGANIZATION_ID") or self.setting("LINKEDIN_REQUEST_ORG_SCOPE").lower() in (
            "1",
            "true",
            "yes",
        ):
            scopes.append("w_organization_social")
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self.setting("LINKEDIN_CLIENT_ID"),
                "redirect_uri": redirect_uri,
                "state": state,
                "scope": " ".join(scopes),
            }
        )
        return _AUTH + "?" + query

    def exchange_code(self, code, redirect_uri, code_verifier=""):
        response = self.transport.request(
            "POST",
            _TOKEN,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": self.setting("LINKEDIN_CLIENT_ID"),
                "client_secret": self.setting("LINKEDIN_CLIENT_SECRET"),
            },
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
                "client_id": self.setting("LINKEDIN_CLIENT_ID"),
                "client_secret": self.setting("LINKEDIN_CLIENT_SECRET"),
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
            _USERINFO,
            headers=bearer(bundle.access_token),
        )
        response.raise_for_status()
        info = response.json()
        person = str(info.get("sub") or "")
        if not person:
            raise PlatformError("LinkedIn userinfo did not return sub")
        name = info.get("name") or "LinkedIn member"
        org = self.setting("LINKEDIN_ORGANIZATION_ID")
        extra = {"person_id": person, "author": "urn:li:person:" + person}
        handle = name
        display = name
        external = person
        if org:
            extra["organization_id"] = org
            extra["author"] = "urn:li:organization:" + org
            handle = "org:" + org
            display = name + " for organization " + org
            external = "org:" + org
        return [
            ConnectedAccount(
                platform=self.platform,
                handle=handle,
                display_name=display,
                external_id=external,
                access_token=bundle.access_token,
                refresh_token=bundle.refresh_token,
                expires_in=bundle.expires_in,
                scopes=list(bundle.scopes or self.scopes),
                extra=extra,
            )
        ]

    def upload_media(self, account, media):
        media = _coerce(media)
        if media.kind == "video":
            raise PlatformNotImplemented(
                "LinkedIn video posts use the Videos API (POST /rest/videos?action=initializeUpload "
                "and a multi-part upload). This adapter publishes images only."
            )
        owner = (account.get("extra") or {}).get("author") or ""
        if not owner:
            raise PlatformError("LinkedIn account is missing an author URN. Reconnect it.")
        response = self.transport.request(
            "POST",
            _IMAGES + "?action=initializeUpload",
            json_body={"initializeUploadRequest": {"owner": owner}},
            headers=self._headers(account),
        )
        response.raise_for_status()
        value = (response.json().get("value") or {})
        upload_url = value.get("uploadUrl") or ""
        image_urn = value.get("image") or ""
        if not upload_url or not image_urn:
            raise PlatformError("LinkedIn image initializeUpload did not return uploadUrl and image")
        content = read_file(media.path)
        uploaded = self.transport.request(
            "PUT",
            upload_url,
            raw=content,
            headers={
                "Authorization": "Bearer " + (account.get("access_token") or ""),
                "Content-Type": media.mime or "image/jpeg",
            },
        )
        uploaded.raise_for_status()
        media.extra_id = image_urn
        return media

    def publish(self, account, media, caption, options=None):
        options = options or {}
        media = self.upload_media(account, media)
        author = (account.get("extra") or {}).get("author") or ""
        visibility = options.get("privacy") or "PUBLIC"
        if visibility not in ("PUBLIC", "CONNECTIONS"):
            visibility = "PUBLIC"
        body = {
            "author": author,
            "commentary": caption or "",
            "visibility": visibility,
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "content": {
                "media": {
                    "id": getattr(media, "extra_id", ""),
                    "title": (caption or "Post")[:200],
                }
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }
        response = self.transport.request(
            "POST",
            _POSTS,
            json_body=body,
            headers=self._headers(account),
        )
        response.raise_for_status()
        remote_id = response.headers.get("x-restli-id") or ""
        if not remote_id:
            try:
                remote_id = str((response.json() or {}).get("id") or "")
            except Exception:
                remote_id = ""
        if not remote_id:
            raise PlatformError("LinkedIn did not return a post id")
        return PublishResult(remote_id=remote_id, permalink="", raw={"id": remote_id})

    def get_status(self, account, remote_id):
        response = self.transport.request(
            "GET",
            _POSTS + "/" + str(remote_id),
            headers=self._headers(account),
        )
        response.raise_for_status()
        payload = response.json()
        return {
            "remote_id": remote_id,
            "status": payload.get("lifecycleState") or "",
            "permalink": "",
            "raw": {"id": payload.get("id"), "lifecycleState": payload.get("lifecycleState")},
        }

    def _headers(self, account):
        headers = bearer(account.get("access_token") or "")
        headers["LinkedIn-Version"] = self.setting("LINKEDIN_API_VERSION", "202410")
        headers["X-Restli-Protocol-Version"] = "2.0.0"
        return headers


def _coerce(media):
    if isinstance(media, MediaSource):
        return media
    return MediaSource(**{key: media[key] for key in media if key in MediaSource.__dataclass_fields__})
