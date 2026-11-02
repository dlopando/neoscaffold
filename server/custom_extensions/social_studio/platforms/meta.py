"""Shared Facebook Login helpers for Instagram and Facebook Pages."""

from urllib.parse import urlencode

from .base import PlatformError, bundle_from_payload

GRAPH = "https://graph.facebook.com"


def graph_version(adapter):
    return adapter.setting("META_GRAPH_VERSION", "v21.0")


def dialog_url(adapter, redirect_uri, state, scopes):
    query = urlencode(
        {
            "client_id": adapter.setting(adapter.client_id_env),
            "redirect_uri": redirect_uri,
            "state": state,
            "response_type": "code",
            "scope": ",".join(scopes),
        }
    )
    return f"https://www.facebook.com/{graph_version(adapter)}/dialog/oauth?{query}"


def exchange_code(adapter, code, redirect_uri):
    response = adapter.transport.request(
        "GET",
        f"{GRAPH}/{graph_version(adapter)}/oauth/access_token",
        params={
            "client_id": adapter.setting(adapter.client_id_env),
            "client_secret": adapter.setting(adapter.client_secret_env),
            "redirect_uri": redirect_uri,
            "code": code,
        },
    )
    response.raise_for_status()
    short = bundle_from_payload(response.json())
    return extend_token(adapter, short)


def extend_token(adapter, bundle):
    response = adapter.transport.request(
        "GET",
        f"{GRAPH}/{graph_version(adapter)}/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": adapter.setting(adapter.client_id_env),
            "client_secret": adapter.setting(adapter.client_secret_env),
            "fb_exchange_token": bundle.access_token,
        },
    )
    response.raise_for_status()
    long_lived = bundle_from_payload(response.json())
    if not long_lived.refresh_token:
        long_lived.refresh_token = ""
    if not long_lived.scopes:
        long_lived.scopes = list(bundle.scopes)
    return long_lived


def refresh_long_lived(adapter, account):
    from .base import TokenBundle

    current = TokenBundle(
        access_token=account.get("access_token") or "",
        refresh_token=account.get("refresh_token") or "",
        scopes=list(account.get("scopes") or []),
    )
    # Page tokens are refreshed by exchanging the user token stored in
    # refresh_token when we saved one. Otherwise extend the current token.
    if account.get("extra", {}).get("token_role") == "page" and account.get("refresh_token"):
        current.access_token = account["refresh_token"]
    return extend_token(adapter, current)


def graph_get(adapter, path, token, params=None):
    query = dict(params or {})
    response = adapter.transport.request(
        "GET",
        f"{GRAPH}/{graph_version(adapter)}/{path.lstrip('/')}",
        params=query,
        headers={"Authorization": "Bearer " + token},
    )
    response.raise_for_status()
    payload = response.json()
    error = payload.get("error")
    if isinstance(error, dict):
        raise PlatformError(
            "Graph error: " + str(error.get("message") or error),
            transient=int(error.get("code") or 0) in (1, 2, 4, 17),
        )
    return payload


def list_pages(adapter, token):
    payload = graph_get(
        adapter,
        "me/accounts",
        token,
        {
            "fields": "id,name,access_token,username,instagram_business_account{id,username,name}"
        },
    )
    return list(payload.get("data") or [])
