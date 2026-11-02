"""HTTP routes for account management, OAuth, and the post log."""

import os
import secrets

from aiohttp import web

from . import pages, paths
from .platforms.registry import catalog, get_adapter, platform_names
from .platforms.x import pkce_challenge
from .scheduler import shift
from .store import expiry_from_seconds, get_store, utc_now

_PREVIEW_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Social Studio workflow</title>
  <style>
    html, body { margin: 0; height: 100%; background: #101218; color: #eee; }
    #graph { width: 100vw; height: 100vh; display: block; }
    #note {
      position: fixed; left: 16px; bottom: 14px; z-index: 5;
      font: 13px/1.4 ui-sans-serif, system-ui, sans-serif;
      background: rgba(12, 14, 18, 0.88); color: #f3f4f6;
      border: 1px solid rgba(255,255,255,0.14); border-radius: 10px;
      padding: 8px 12px; max-width: 560px;
    }
  </style>
</head>
<body>
  <canvas id="graph"></canvas>
  <div id="note">Ad Studio creatives feed caption variations, then DISTRIBUTE / POST with dry run on. Open Accounts to connect platforms.</div>
  <script src="/social-studio/vendor/litegraph.js"></script>
  <script src="/ad-studio/client.js"></script>
  <script src="/social-studio/client.js"></script>
  <script>
    function fitGraph(canvas, graph) {
      var nodes = graph._nodes || [];
      if (!nodes.length || !canvas.ds) return;
      var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      nodes.forEach(function (node) {
        var x = node.pos[0], y = node.pos[1];
        minX = Math.min(minX, x); minY = Math.min(minY, y - 30);
        maxX = Math.max(maxX, x + node.size[0]); maxY = Math.max(maxY, y + node.size[1]);
      });
      var pad = 48, viewW = canvas.canvas.width, viewH = canvas.canvas.height;
      var scale = Math.min(viewW / (maxX - minX + pad * 2), viewH / (maxY - minY + pad * 2));
      scale = Math.max(0.12, Math.min(scale, 1));
      canvas.ds.scale = scale;
      canvas.ds.offset[0] = (viewW / 2) / scale - (minX + maxX) / 2;
      canvas.ds.offset[1] = (viewH / 2) / scale - (minY + maxY) / 2;
      canvas.setDirty(true, true);
    }
    async function boot() {
      var element = document.getElementById("graph");
      element.width = window.innerWidth; element.height = window.innerHeight;
      var graph = new LGraph();
      var canvas = new LGraphCanvas(element, graph);
      canvas.clear_background_color = "#101218";
      var response = await fetch("/social-studio/workflows/social_studio_dry_run.json");
      if (!response.ok) throw new Error("workflow HTTP " + response.status);
      graph.configure(await response.json());
      graph.start();
      fitGraph(canvas, graph);
      window.__socialStudioReady = true;
    }
    boot().catch(function (error) {
      document.getElementById("note").textContent = "Social Studio preview failed: " + error.message;
      window.__socialStudioReady = true;
    });
  </script>
</body>
</html>
"""


def _authorize(request):
    """Same gate as the rest of NeoScaffold. Auth off means the local operator."""
    if str(os.getenv("NEOSCAFFOLD_AUTH_ENABLED", "")).lower() != "true":
        return {"user_info": {"user_id": "neoscaffold_user"}, "proto_list": ["json"]}
    from server.domain.utilities.authorize_user_and_get_info import (
        authorize_user_and_get_info,
    )

    return authorize_user_and_get_info(request)


def _wants_json(request):
    content = request.headers.get("Content-Type", "")
    accept = request.headers.get("Accept", "")
    return "application/json" in content or "application/json" in accept


def _safe_id(value):
    text = str(value or "")
    if len(text) == 32 and all(character in "0123456789abcdef" for character in text):
        return text
    return ""


def register_routes(server):
    routes = server.routes

    @routes.get("/social-studio/accounts")
    async def accounts_html(request):
        store = get_store(server)
        demo = request.query.get("demo") == "1"
        accounts = [] if demo else store.list_accounts()
        placeholder = demo or not accounts
        notice = ""
        if request.query.get("connected"):
            notice = "Connected " + request.query.get("connected") + ". The token was stored encrypted."
        if request.query.get("removed"):
            notice = "Account removed."
        return web.Response(
            text=pages.accounts_page(
                pages.placeholder_accounts() if placeholder else accounts,
                catalog(),
                placeholder=placeholder,
                notice=notice,
            ),
            content_type="text/html",
        )

    @routes.get("/social-studio/accounts.json")
    async def accounts_json(_request):
        return web.json_response({"accounts": get_store(server).list_accounts()})

    @routes.get("/social-studio/setup.json")
    async def setup_json(_request):
        described = []
        for item in catalog():
            described.append(
                {
                    "platform": item["platform"],
                    "label": item["label"],
                    "configured": item["configured"],
                    "missing": item["missing"],
                    "redirect_uri": item["redirect_uri"],
                    "scopes": item["scopes"],
                    "implements": item["implements"],
                    "not_implemented": item["not_implemented"],
                }
            )
        return web.json_response({"platforms": described})

    @routes.post("/social-studio/accounts")
    async def add_account(request):
        info = _authorize(request)
        if isinstance(info, web.Response):
            return info
        if _wants_json(request):
            try:
                body = await request.json()
            except Exception:
                return web.json_response({"error": "invalid JSON"}, status=400)
        else:
            body = await request.post()
        platform = str(body.get("platform") or "").strip().lower()
        if platform not in platform_names():
            return web.json_response({"error": "unknown platform"}, status=400)
        handle = str(body.get("handle") or "").strip()
        if not handle:
            return web.json_response({"error": "handle is required"}, status=400)
        if not os.environ.get("SOCIAL_STUDIO_SECRET_KEY"):
            return web.json_response(
                {"error": "SOCIAL_STUDIO_SECRET_KEY is not set"}, status=400
            )
        tags = _tags(body.get("tags"))
        try:
            expires_in = int(body.get("expires_in") or 0)
        except (TypeError, ValueError):
            expires_in = 0
        account = get_store(server).upsert_account(
            platform=platform,
            handle=handle,
            display_name=str(body.get("display_name") or handle),
            external_id=str(body.get("external_id") or ""),
            tags=tags,
            token_expiry=expiry_from_seconds(expires_in) if expires_in else "",
            access_token=str(body.get("access_token") or ""),
            refresh_token=str(body.get("refresh_token") or ""),
            scopes=_tags(body.get("scopes")),
            extra={"source": "manual"},
        )
        if _wants_json(request):
            return web.json_response({"account": account})
        raise web.HTTPFound("/social-studio/accounts?connected=" + platform)

    @routes.post("/social-studio/groups")
    async def group_accounts(request):
        info = _authorize(request)
        if isinstance(info, web.Response):
            return info
        body = await _body(request)
        tag = str(body.get("tag") or "").strip()
        if not tag:
            return web.json_response({"error": "tag is required"}, status=400)
        store = get_store(server)
        updated = []
        for account_id in _tags(body.get("ids")):
            safe = _safe_id(account_id)
            if not safe:
                continue
            if str(body.get("op") or "add") == "remove":
                account = store.remove_tag(safe, tag)
            else:
                account = store.add_tag(safe, tag)
            if account:
                updated.append(account)
        return web.json_response({"accounts": updated})

    @routes.post("/social-studio/accounts/{account_id}/tag")
    async def tag_account(request):
        info = _authorize(request)
        if isinstance(info, web.Response):
            return info
        account_id = _safe_id(request.match_info["account_id"])
        if not account_id:
            return web.json_response({"error": "unknown account"}, status=404)
        body = await _body(request)
        tag = str(body.get("tag") or "").strip()
        store = get_store(server)
        if str(body.get("op") or "add") == "remove":
            account = store.remove_tag(account_id, tag)
        else:
            account = store.add_tag(account_id, tag)
        if not account:
            return web.json_response({"error": "unknown account"}, status=404)
        if _wants_json(request):
            return web.json_response({"account": account})
        raise web.HTTPFound("/social-studio/accounts")

    @routes.post("/social-studio/accounts/{account_id}/delete")
    async def delete_account_form(request):
        return await _delete(server, request)

    @routes.delete("/social-studio/accounts/{account_id}")
    async def delete_account(request):
        return await _delete(server, request)

    @routes.get("/social-studio/connect/{platform}")
    async def connect(request):
        info = _authorize(request)
        if isinstance(info, web.Response):
            return info
        platform = request.match_info["platform"]
        if platform not in platform_names():
            return web.Response(
                text=pages.message_page("Unknown platform", platform),
                content_type="text/html",
                status=404,
            )
        adapter = get_adapter(platform)
        missing = adapter.missing_settings()
        redirect_uri = adapter.redirect_uri()
        if missing or not redirect_uri:
            detail = ", ".join(missing)
            if not redirect_uri:
                detail = (detail + ", " if detail else "") + (
                    platform.upper() + "_REDIRECT_URI or SOCIAL_STUDIO_PUBLIC_BASE"
                )
            return web.Response(
                text=pages.message_page(
                    "Connect " + adapter.label,
                    "Set these environment variables, then try again: " + detail,
                    "Developer app steps are in custom_extensions/social_studio/README.md.",
                ),
                content_type="text/html",
                status=400,
            )
        state = secrets.token_urlsafe(24)
        verifier = secrets.token_urlsafe(48)
        get_store(server).save_oauth_state(
            state=state,
            platform=platform,
            code_verifier=verifier,
            redirect_uri=redirect_uri,
        )
        url = adapter.authorization_url(state, redirect_uri, pkce_challenge(verifier))
        raise web.HTTPFound(url)

    @routes.get("/social-studio/oauth/{platform}/callback")
    async def oauth_callback(request):
        platform = request.match_info["platform"]
        if request.query.get("error"):
            return web.Response(
                text=pages.message_page(
                    "Connect failed",
                    str(request.query.get("error_description") or request.query.get("error")),
                ),
                content_type="text/html",
                status=400,
            )
        state = str(request.query.get("state") or "")
        code = str(request.query.get("code") or "")
        saved = get_store(server).pop_oauth_state(state)
        if not saved or saved["platform"] != platform or not code:
            return web.Response(
                text=pages.message_page(
                    "Connect failed",
                    "This connect link is invalid or has already been used.",
                ),
                content_type="text/html",
                status=400,
            )
        if saved["created_at"] < shift(utc_now(), -900):
            return web.Response(
                text=pages.message_page("Connect failed", "This connect link expired."),
                content_type="text/html",
                status=400,
            )
        try:
            adapter = get_adapter(platform)
            bundle = adapter.exchange_code(code, saved["redirect_uri"], saved["code_verifier"])
            connected = adapter.fetch_accounts(bundle)
        except Exception as exc:
            return web.Response(
                text=pages.message_page("Connect failed", str(exc)[:500]),
                content_type="text/html",
                status=400,
            )
        store = get_store(server)
        expiry = expiry_from_seconds(bundle.expires_in) if bundle.expires_in else ""
        for account in connected:
            store.upsert_account(
                platform=account.platform,
                handle=account.handle,
                display_name=account.display_name,
                external_id=account.external_id,
                status="connected",
                token_expiry=expiry,
                access_token=account.access_token,
                refresh_token=account.refresh_token,
                scopes=account.scopes,
                extra=account.extra,
            )
        raise web.HTTPFound("/social-studio/accounts?connected=" + platform)

    @routes.get("/social-studio/plan")
    async def plan_html(request):
        demo = request.query.get("demo") == "1"
        plan = None if demo else get_store(server).latest_plan()
        return web.Response(
            text=pages.plan_page(plan, placeholder=demo or not plan),
            content_type="text/html",
        )

    @routes.get("/social-studio/log")
    async def log_html(request):
        demo = request.query.get("demo") == "1"
        posts = [] if demo else get_store(server).list_posts(100)
        return web.Response(
            text=pages.log_page(posts, placeholder=demo or not posts),
            content_type="text/html",
        )

    @routes.get("/social-studio/media/{name}")
    async def media(request):
        path = paths.contained_file(paths.media_dir(server), request.match_info["name"])
        if not path or not os.path.isfile(path):
            return web.json_response({"error": "not found"}, status=404)
        return web.FileResponse(path)

    @routes.get("/social-studio/workflows/social_studio_dry_run.json")
    async def workflow(_request):
        workflow_path = paths.example_workflow_path()
        if not os.path.isfile(workflow_path):
            return web.json_response({"error": "example workflow is missing"}, status=404)
        return web.FileResponse(workflow_path)

    @routes.get("/social-studio/client.js")
    async def client_js(_request):
        javascript = (server.extensions.get("social_studio") or {}).get("javascript") or ""
        if not javascript:
            javascript = _read_web_js()
        if not javascript:
            return web.Response(status=404, text="social studio client is not loaded")
        return web.Response(text=javascript, content_type="application/javascript")

    @routes.get("/social-studio/vendor/litegraph.js")
    async def litegraph(_request):
        path = paths.litegraph_path()
        if not os.path.isfile(path):
            return web.Response(status=404, text="litegraph.js not found")
        return web.FileResponse(path)

    @routes.get("/social-studio/preview")
    async def preview(_request):
        return web.Response(text=_PREVIEW_HTML, content_type="text/html")


async def _delete(server, request):
    info = _authorize(request)
    if isinstance(info, web.Response):
        return info
    account_id = _safe_id(request.match_info["account_id"])
    if not account_id or not get_store(server).get_account(account_id):
        return web.json_response({"error": "unknown account"}, status=404)
    get_store(server).remove_account(account_id)
    if _wants_json(request):
        return web.json_response({"removed": account_id})
    raise web.HTTPFound("/social-studio/accounts?removed=1")


async def _body(request):
    if _wants_json(request):
        try:
            return await request.json()
        except Exception:
            return {}
    return await request.post()


def _tags(value):
    if isinstance(value, (list, tuple)):
        parts = value
    else:
        parts = str(value or "").replace(";", ",").split(",")
    tags = []
    for part in parts:
        text = str(part or "").strip()
        if text and text not in tags:
            tags.append(text)
    return tags


def _read_web_js():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web.js")
    if not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()
