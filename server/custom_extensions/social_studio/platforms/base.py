"""Shared adapter types and the HTTP transport.

Adapters call ``Transport.request``. Tests pass a fake transport.
Error text uses the URL path only, so a client secret in a query string
cannot leak through an exception.
"""

import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field


class PlatformError(RuntimeError):
    def __init__(self, message, transient=False, status=0):
        super().__init__(message)
        self.transient = transient
        self.status = status


class PlatformNotImplemented(NotImplementedError):
    """The official API surface for this action is not wired up."""


@dataclass
class TokenBundle:
    access_token: str
    refresh_token: str = ""
    expires_in: int = 0
    scopes: list = field(default_factory=list)
    raw: dict = field(default_factory=dict)


@dataclass
class ConnectedAccount:
    platform: str
    handle: str
    display_name: str
    external_id: str
    access_token: str
    refresh_token: str = ""
    expires_in: int = 0
    scopes: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)


@dataclass
class MediaSource:
    path: str = ""
    url: str = ""
    kind: str = "image"
    mime: str = ""
    filename: str = ""
    width: int = 0
    height: int = 0
    aspect: str = ""


@dataclass
class PublishResult:
    remote_id: str
    permalink: str = ""
    raw: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)


class HTTPResponse:
    def __init__(self, status, headers, content, url):
        self.status = int(status)
        self.headers = {str(key).lower(): value for key, value in (headers or {}).items()}
        self.content = content or b""
        self.url = url

    def json(self):
        if not self.content:
            return {}
        return json.loads(self.content.decode("utf-8"))

    def raise_for_status(self):
        if 200 <= self.status < 300:
            return
        transient = self.status in (408, 429, 500, 502, 503, 504)
        body = self.content[:400].decode("utf-8", "replace")
        raise PlatformError(
            f"HTTP {self.status} {safe_url(self.url)}: {body}",
            transient=transient,
            status=self.status,
        )


class UrllibTransport:
    def request(
        self,
        method,
        url,
        *,
        headers=None,
        params=None,
        data=None,
        json_body=None,
        files=None,
        raw=None,
        timeout=60,
    ):
        headers = {str(key): str(value) for key, value in dict(headers or {}).items()}
        if params:
            query = urllib.parse.urlencode({key: value for key, value in params.items() if value is not None})
            url = url + ("&" if "?" in url else "?") + query
        body = None
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
        elif files is not None:
            body, content_type = encode_multipart(data or {}, files)
            headers["Content-Type"] = content_type
        elif raw is not None:
            body = raw if isinstance(raw, bytes) else str(raw).encode("utf-8")
        elif data is not None:
            body = urllib.parse.urlencode(data).encode("utf-8")
            headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
        request = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return HTTPResponse(response.status, dict(response.headers), response.read(), url)
        except urllib.error.HTTPError as exc:
            payload = exc.read() if hasattr(exc, "read") else b""
            return HTTPResponse(exc.code, dict(exc.headers or {}), payload, url)
        except urllib.error.URLError as exc:
            raise PlatformError(
                f"network error {safe_url(url)}: {exc.reason}",
                transient=True,
            ) from exc


def encode_multipart(fields, files):
    boundary = "----SocialStudio" + secrets.token_hex(12)
    chunks = []
    for key, value in (fields or {}).items():
        chunks.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'
                f"{value}\r\n"
            ).encode("utf-8")
        )
    for key, fileinfo in (files or {}).items():
        filename, content, mime = fileinfo
        header = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{key}"; filename="{filename}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode("utf-8")
        chunks.append(header + content + b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), "multipart/form-data; boundary=" + boundary


def safe_url(url):
    return str(url or "").split("?", 1)[0]


# Present on the setup page, but a blank value is a valid configuration.
_OPTIONAL_ENV = {
    "TIKTOK_CONTENT_POSTING_AUDITED",
    "LINKEDIN_ORGANIZATION_ID",
    "LINKEDIN_API_VERSION",
    "LINKEDIN_REQUEST_ORG_SCOPE",
    "META_GRAPH_VERSION",
    "META_APP_ID",
    "META_APP_SECRET",
}


def bearer(token):
    return {"Authorization": "Bearer " + str(token or "")}


def read_file(path):
    if not path:
        raise PlatformError("media path is empty")
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError as exc:
        raise PlatformError(f"could not read media file: {exc.strerror or exc}") from exc


def oauth_error(payload):
    if not isinstance(payload, dict):
        return ""
    error = payload.get("error")
    if isinstance(error, dict):
        code = error.get("code") or ""
        message = error.get("message") or ""
        if code and str(code).lower() not in ("ok", "0", ""):
            return f"{code}: {message}".strip()
        return ""
    if error:
        description = payload.get("error_description") or payload.get("message") or ""
        return f"{error}: {description}".strip(": ")
    return ""


def bundle_from_payload(payload):
    message = oauth_error(payload)
    if message:
        raise PlatformError("token endpoint rejected the grant: " + message)
    access = str(payload.get("access_token") or "")
    if not access:
        raise PlatformError("token endpoint returned no access_token")
    expires = payload.get("expires_in") or 0
    try:
        expires = int(expires)
    except (TypeError, ValueError):
        expires = 0
    scope = payload.get("scope") or ""
    if isinstance(scope, str):
        scopes = [part for part in scope.replace(",", " ").split() if part]
    elif isinstance(scope, list):
        scopes = [str(part) for part in scope]
    else:
        scopes = []
    raw = {
        key: value
        for key, value in payload.items()
        if key not in ("access_token", "refresh_token", "id_token")
    }
    return TokenBundle(
        access_token=access,
        refresh_token=str(payload.get("refresh_token") or ""),
        expires_in=expires,
        scopes=scopes,
        raw=raw,
    )


class PlatformAdapter:
    """Official-API adapter. Subclasses implement the five operations."""

    platform = ""
    label = ""
    scopes = ()
    docs_url = ""
    audit_notes = ()
    implements = ()
    not_implemented = ()
    env_vars = ()

    def __init__(self, transport=None, env=None):
        self.transport = transport or UrllibTransport()
        self.env = env

    def setting(self, name, default=""):
        source = self.env
        if source is None:
            import os

            source = os.environ
        value = source.get(name)
        if value is None or str(value).strip() == "":
            return default
        return str(value).strip()

    def configured(self):
        return not self.missing_settings()

    def missing_settings(self):
        missing = []
        for name in self.env_vars:
            if name.endswith("_REDIRECT_URI") or name in _OPTIONAL_ENV:
                continue
            if not self.setting(name):
                missing.append(name)
        return missing

    def redirect_uri(self):
        for name in self.env_vars:
            if name.endswith("_REDIRECT_URI") and self.setting(name):
                return self.setting(name)
        import os

        base = self.setting("SOCIAL_STUDIO_PUBLIC_BASE").rstrip("/")
        if not base:
            base = os.environ.get("SOCIAL_STUDIO_PUBLIC_BASE", "").rstrip("/")
        if not base:
            return ""
        return base + "/social-studio/oauth/" + self.platform + "/callback"

    def describe(self):
        return {
            "platform": self.platform,
            "label": self.label,
            "scopes": list(self.scopes),
            "docs_url": self.docs_url,
            "audit_notes": list(self.audit_notes),
            "implements": list(self.implements),
            "not_implemented": list(self.not_implemented),
            "env_vars": list(self.env_vars),
            "configured": self.configured(),
            "missing": self.missing_settings(),
            "redirect_uri": self.redirect_uri(),
        }

    def authorization_url(self, state, redirect_uri, code_challenge=""):
        raise PlatformNotImplemented(self.platform + " connect is not implemented")

    def exchange_code(self, code, redirect_uri, code_verifier=""):
        raise PlatformNotImplemented(self.platform + " token exchange is not implemented")

    def refresh(self, account):
        raise PlatformNotImplemented(self.platform + " token refresh is not implemented")

    def fetch_accounts(self, bundle):
        raise PlatformNotImplemented(self.platform + " profile lookup is not implemented")

    def upload_media(self, account, media):
        raise PlatformNotImplemented(self.platform + " media upload is not implemented")

    def publish(self, account, media, caption, options=None):
        raise PlatformNotImplemented(self.platform + " publish is not implemented")

    def get_status(self, account, remote_id):
        raise PlatformNotImplemented(self.platform + " status is not implemented")
