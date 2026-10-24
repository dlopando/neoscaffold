"""HTTP routes for Ad Studio uploads, generated stills, and the preview canvas."""

import os

from aiohttp import web

from . import imaging, paths
from .styles import load_styles

_PREVIEW_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Ad Studio preview</title>
  <style>
    html, body { margin: 0; height: 100%; background: #101218; color: #eee; }
    #graph { width: 100vw; height: 100vh; display: block; }
    #note {
      position: fixed; left: 16px; bottom: 14px; z-index: 5;
      font: 13px/1.4 ui-sans-serif, system-ui, sans-serif;
      background: rgba(12, 14, 18, 0.88); color: #f3f4f6;
      border: 1px solid rgba(255,255,255,0.14); border-radius: 10px;
      padding: 8px 12px; max-width: 520px;
    }
  </style>
</head>
<body>
  <canvas id="graph"></canvas>
  <div id="note">Ad Studio canvas. Placeholder stills are labeled PLACEHOLDER. Green border = favorite. Red = discarded (muted, skipped on the next run).</div>
  <script src="/ad-studio/vendor/litegraph.js"></script>
  <script src="/ad-studio/client.js"></script>
  <script>
    function fitGraph(canvas, graph) {
      var nodes = graph._nodes || [];
      if (!nodes.length || !canvas.ds) return;
      var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      nodes.forEach(function (node) {
        var x = node.pos[0], y = node.pos[1];
        minX = Math.min(minX, x);
        minY = Math.min(minY, y - 30);
        maxX = Math.max(maxX, x + node.size[0]);
        maxY = Math.max(maxY, y + node.size[1]);
      });
      var pad = 48;
      var viewW = canvas.canvas.width;
      var viewH = canvas.canvas.height;
      var scale = Math.min(viewW / (maxX - minX + pad * 2), viewH / (maxY - minY + pad * 2));
      scale = Math.max(0.12, Math.min(scale, 1));
      var centerX = (minX + maxX) / 2;
      var centerY = (minY + maxY) / 2;
      canvas.ds.scale = scale;
      canvas.ds.offset[0] = (viewW / 2) / scale - centerX;
      canvas.ds.offset[1] = (viewH / 2) / scale - centerY;
      canvas.setDirty(true, true);
    }

    async function boot() {
      var element = document.getElementById("graph");
      element.width = window.innerWidth;
      element.height = window.innerHeight;
      var graph = new LGraph();
      var canvas = new LGraphCanvas(element, graph);
      canvas.clear_background_color = "#101218";
      canvas.background_image = LGraphCanvas.DEFAULT_BACKGROUND_IMAGE || canvas.background_image;
      window.__adStudioCanvas = canvas;
      window.__adStudioGraph = graph;
      var response = await fetch("/ad-studio/workflows/ad_studio_40.json");
      if (!response.ok) throw new Error("workflow HTTP " + response.status);
      graph.configure(await response.json());
      graph.start();
      fitGraph(canvas, graph);
      window.addEventListener("resize", function () {
        element.width = window.innerWidth;
        element.height = window.innerHeight;
        fitGraph(canvas, graph);
      });
      setTimeout(function () { window.__adStudioReady = true; }, 600);
    }
    boot().catch(function (error) {
      document.getElementById("note").textContent = "Ad Studio preview failed: " + error.message;
      window.__adStudioReady = true;
    });
  </script>
</body>
</html>
"""


def _authorize(request):
    from server.domain.utilities.authorize_user_and_get_info import (
        authorize_user_and_get_info,
    )

    return authorize_user_and_get_info(request)


def _file(directory, name):
    path = paths.contained_file(directory, name)
    if not path or not os.path.isfile(path):
        return web.json_response({"error": "not found"}, status=404)
    return web.FileResponse(path)


def register_routes(server):
    routes = server.routes

    @routes.get("/ad-studio/styles")
    async def ad_studio_styles(_request):
        return web.json_response({"styles": load_styles()})

    @routes.get("/ad-studio/outputs/{name}")
    async def ad_studio_output(request):
        return _file(paths.output_dir(server), request.match_info["name"])

    @routes.get("/ad-studio/inputs/{name}")
    async def ad_studio_input(request):
        return _file(paths.input_dir(server), request.match_info["name"])

    @routes.get("/ad-studio/placeholders/{name}")
    async def ad_studio_placeholder(request):
        name = request.match_info["name"]
        style_id = name[:-4] if name.lower().endswith(".png") else name
        imaging.ensure_placeholder(style_id, server=server)
        filename = paths.safe_filename(style_id) + ".png"
        return _file(paths.placeholder_dir(server), filename)

    @routes.get("/ad-studio/workflows/ad_studio_40.json")
    async def ad_studio_workflow(_request):
        workflow = paths.example_workflow_path()
        if not os.path.isfile(workflow):
            return web.json_response(
                {"error": "example workflow is missing. Run build_workflow.py."},
                status=404,
            )
        return web.FileResponse(workflow)

    @routes.get("/ad-studio/client.js")
    async def ad_studio_client(_request):
        javascript = (server.extensions.get("ad_studio") or {}).get("javascript") or ""
        if not javascript:
            return web.Response(status=404, text="ad studio client is not loaded")
        return web.Response(text=javascript, content_type="application/javascript")

    @routes.get("/ad-studio/vendor/litegraph.js")
    async def ad_studio_litegraph(_request):
        path = paths.litegraph_path()
        if not os.path.isfile(path):
            return web.Response(status=404, text="litegraph.js not found")
        return web.FileResponse(path)

    @routes.get("/ad-studio/preview")
    async def ad_studio_preview(_request):
        return web.Response(text=_PREVIEW_HTML, content_type="text/html")

    @routes.post("/ad-studio/upload")
    async def ad_studio_upload(request):
        info = _authorize(request)
        if isinstance(info, web.Response):
            return info
        reader = await request.multipart()
        field = await reader.next()
        if field is None or field.name != "image":
            return web.json_response(
                {"error": "expected multipart field 'image'"}, status=400
            )
        original = field.filename or "upload.png"
        extension = os.path.splitext(original)[1].lower()
        if extension == ".jpeg":
            extension = ".jpg"
        if extension not in (".png", ".jpg", ".webp"):
            return web.json_response(
                {"error": "upload a png, jpg, or webp"}, status=400
            )
        data = await field.read(decode=False)
        if not data:
            return web.json_response({"error": "empty upload"}, status=400)
        if len(data) > 20 * 1024 * 1024:
            return web.json_response({"error": "image exceeds 20MB"}, status=413)
        filename = f"upload-{os.urandom(6).hex()}{extension}"
        path = os.path.join(paths.input_dir(server), filename)
        with open(path, "wb") as handle:
            handle.write(data)
        return web.json_response(
            {
                "filename": filename,
                "path": path,
                "url": f"/ad-studio/inputs/{filename}",
            }
        )
