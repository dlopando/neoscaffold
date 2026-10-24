"""Ad Studio nodes, prompt composition, and HTTP routes. OpenAI is mocked."""

import asyncio
import io
import json
from argparse import Namespace

from aiohttp.test_utils import TestClient, TestServer
from PIL import Image

from custom_extensions.ad_studio.brand import build_brief, parse_html
from custom_extensions.ad_studio.build_workflow import build_workflow
from custom_extensions.ad_studio.extension import (
    AdBrandBrief,
    AdCreative,
    AdFrame916,
    AdProductImage,
)
from custom_extensions.ad_studio.imaging import (
    default_image_editor,
    frame_image,
    render_placeholder,
)
from custom_extensions.ad_studio.prompts import SAMPLE_BRIEF, compose_prompt
from custom_extensions.ad_studio.styles import load_styles
from server.domain.services.graph_executor import GraphExecutor
from server.infrastructure.servers.server import Server


class FakeEditor:
    def __init__(self):
        self.calls = []

    def edit(self, prompt, image_paths, size, model):
        self.calls.append(
            {
                "prompt": prompt,
                "image_paths": list(image_paths),
                "size": size,
                "model": model,
            }
        )
        image = Image.new("RGB", (48, 64), (12, 140, 90))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()


class FakeExtractor:
    def extract(self, page_text, product_name, url):
        return {
            "brand_name": "Luma",
            "product_name": product_name,
            "tagline": "Glow, without the guesswork",
            "tone": "witty",
            "colors": ["#112233"],
            "claims": ["fragrance free"],
            "audience": "skeptical shoppers",
            "category": "serum",
            "page_excerpt": page_text[:80],
        }


def _png(path, color=(20, 20, 20)):
    image = Image.new("RGB", (16, 16), color)
    image.save(path, format="PNG")
    return path


def _server_stub(tmp_path):
    class Stub:
        output_directory = str(tmp_path / "out")
        input_directory = str(tmp_path / "in")

    return Stub()


def _inputs(required=None, optional=None):
    def pack(values):
        return {key: {"values": value} for key, value in (values or {}).items()}

    return {"required_inputs": pack(required), "optional_inputs": pack(optional)}


def test_style_library_has_forty_unique_styles():
    styles = load_styles()
    ids = [style["id"] for style in styles]
    assert len(styles) == 40
    assert len(set(ids)) == 40
    assert "claymation" in ids
    assert "imessage_thread" in ids
    assert "fake_tweet" in ids
    assert "dont_buy_this" in ids
    assert "eight_signs" in ids
    assert "ninety_seven" in ids
    assert "were_so_sorry" in ids
    assert any(style["aspect"] == "9:16" for style in styles)


def test_compose_prompt_keeps_headline_brand_and_favorites():
    style = next(style for style in load_styles() if style["id"] == "dont_buy_this")
    prompt = compose_prompt(
        style,
        SAMPLE_BRIEF,
        favorites=[{"style_name": "Claymation", "prompt": "a clay bottle"}],
        variation="tighter crop",
    )
    assert "Luma Serum" in prompt
    assert "DON'T BUY THIS Luma Serum" in prompt
    assert "Claymation" in prompt
    assert "tighter crop" in prompt
    assert "real product" in prompt.lower()


def test_frame_image_is_exact_vertical_size():
    raw = render_placeholder(
        {
            "id": "x",
            "name": "X",
            "color": "#FF00AA",
            "headline": "WAIT",
            "aspect": "1:1",
        },
        SAMPLE_BRIEF,
        aspect="1:1",
    )
    framed = frame_image(raw, 1080, 1920, fit="cover")
    with Image.open(io.BytesIO(framed)) as image:
        assert image.size == (1080, 1920)
    padded = frame_image(raw, 1080, 1920, fit="pad")
    with Image.open(io.BytesIO(padded)) as image:
        assert image.size == (1080, 1920)


def test_parse_html_drops_scripts_and_keeps_title():
    page = parse_html(
        "<html><title>Luma | Serum</title><style>.x{color:#fff}</style>"
        "<script>secret()</script><meta name='description' content='Glow daily'>"
        "<p>Real copy</p></html>"
    )
    assert "Luma" in page["title"]
    assert "secret" not in page["text"]
    assert "Real copy" in page["text"]
    assert "Glow daily" in page["description"]


def test_brand_node_uses_extractor_and_skips_network(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "custom_extensions.ad_studio.brand.fetch_page",
        lambda url, timeout=20.0, max_bytes=1_500_000: {
            "title": "Luma",
            "description": "A serum",
            "text": "glass dropper",
            "colors": ["#AABBCC"],
        },
    )
    monkeypatch.setattr(
        AdBrandBrief, "extractor_factory", staticmethod(lambda: FakeExtractor())
    )
    node = AdBrandBrief()
    node._memory = {"server": _server_stub(tmp_path)}
    brief = node.evaluate(
        _inputs(
            {"website_url": "https://example.com/serum", "product_name": "Luma Serum"},
            {"extra_notes": "keep the dropper"},
        )
    )
    assert brief["brand_name"] == "Luma"
    assert brief["product_name"] == "Luma Serum"
    assert brief["extractor"] == "llm"
    assert brief["extra_notes"] == "keep the dropper"


def test_brand_heuristic_when_key_missing(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    brief = build_brief(
        "Luma Serum",
        "https://example.com",
        page={
            "title": "Example Domain",
            "description": "An example.",
            "text": "hello",
            "colors": [],
        },
        extractor=None,
    )
    assert brief["extractor"] == "heuristic"
    assert brief["product_name"] == "Luma Serum"
    assert "OPENAI_API_KEY" in brief.get("note", "")


def test_creative_edits_with_product_and_favorite_reference(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    product = _png(tmp_path / "product.png", (200, 40, 40))
    favorite = _png(tmp_path / "favorite.png", (40, 40, 200))
    editor = FakeEditor()
    AdCreative.image_editor_factory = staticmethod(lambda: editor)
    try:
        node = AdCreative()
        node._memory = {"server": _server_stub(tmp_path)}
        result = node.evaluate(
            _inputs(
                {
                    "brand_brief": SAMPLE_BRIEF,
                    "product_image": {"image_path": str(product)},
                },
                {
                    "style_id": "claymation",
                    "aspect": "9:16",
                    "refine_prompt": "no",
                    "favorites_json": json.dumps(
                        [
                            {
                                "style_name": "Tweet",
                                "prompt": "a post",
                                "image_path": str(favorite),
                            }
                        ]
                    ),
                    "variation": "louder type",
                },
            )
        )
    finally:
        AdCreative.image_editor_factory = staticmethod(default_image_editor)

    assert editor.calls[0]["image_paths"][0] == str(product)
    assert str(favorite) in editor.calls[0]["image_paths"]
    assert editor.calls[0]["size"] == "1024x1536"
    assert editor.calls[0]["model"] == "gpt-image-2"
    assert "louder type" in result["prompt"]
    assert result["placeholder"] is False
    assert result["aspect"] == "9:16"
    assert (result["width"], result["height"]) == (1080, 1920)
    assert result["image_path"].endswith(".png")
    assert result["image_url"].startswith("/ad-studio/outputs/")
    with Image.open(result["image_path"]) as image:
        assert image.size == (1080, 1920)


def test_creative_without_api_key_saves_labeled_placeholder(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    product = _png(tmp_path / "product.png")
    node = AdCreative()
    node._memory = {"server": _server_stub(tmp_path)}
    result = node.evaluate(
        _inputs(
            {"brand_brief": SAMPLE_BRIEF, "product_image": str(product)},
            {
                "style_id": "dont_buy_this",
                "aspect": "style",
                "variation": "calmer color",
            },
        )
    )
    assert result["placeholder"] is True
    assert result["model"] == "placeholder"
    assert "DON'T BUY THIS" in result["prompt"]
    with open(result["image_path"], "rb") as handle:
        assert handle.read(8) == b"\x89PNG\r\n\x1a\n"


def test_product_and_frame_nodes(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    stub = _server_stub(tmp_path)
    product_node = AdProductImage()
    product_node._memory = {"server": stub}
    product = product_node.evaluate(
        _inputs({"image_path": "/ad-studio/placeholders/product.png"})
    )
    assert product["image_path"].endswith("product.png")
    assert product["image_url"].endswith("/product.png")

    creative = AdCreative()
    creative._memory = {"server": stub}
    still = creative.evaluate(
        _inputs(
            {"brand_brief": SAMPLE_BRIEF, "product_image": product},
            {"style_id": "swiss_minimal", "variation": "fixed"},
        )
    )
    frame = AdFrame916()
    frame._memory = {"server": stub}
    vertical = frame.evaluate(_inputs({"image": still}, {"fit": "pad"}))
    assert vertical["width"] == 1080
    assert vertical["height"] == 1920
    assert vertical["model"] == "frame"
    with Image.open(vertical["image_path"]) as image:
        assert image.size == (1080, 1920)


def test_example_workflow_fans_out_to_forty_creatives():
    workflow = build_workflow()
    creatives = [
        node for node in workflow["nodes"] if node["type"] == "ad_studio/AdCreative"
    ]
    assert len(creatives) == 40
    assert workflow["nodes"][0]["title"] == "BRAND WEBSITE + PRODUCT NAME"
    assert workflow["nodes"][1]["title"] == "PRODUCT IMAGE"
    styles = [node["widgets_values"][0] for node in creatives]
    assert len(set(styles)) == 40
    discarded = [node for node in creatives if node["mode"] == 2]
    favorites = [
        node for node in creatives if node["properties"]["ad_studio"].get("favorite")
    ]
    assert len(discarded) == 1
    assert len(favorites) == 1
    assert discarded[0]["properties"]["ad_studio"]["preview_url"]
    link_targets = {(link[3], link[4], link[5]) for link in workflow["links"]}
    for creative in creatives:
        assert (creative["id"], 2, "brand_brief") in link_targets
        assert (creative["id"], 3, "product_image") in link_targets
    frame = next(
        node for node in workflow["nodes"] if node["type"] == "ad_studio/AdFrame916"
    )
    assert any(
        link[3] == frame["id"] and link[5] == "ad_image" for link in workflow["links"]
    )
    assert any(style["aspect"] == "9:16" for style in load_styles())


class _ExecServer:
    def __init__(self, tmp_path):
        self.ENABLE_SMART_CACHE = False
        self.INSPECTION_DELAY = 0
        self.MAX_PARALLEL_NODES = 4
        self.client_id = "ad"
        self.current_workflow_id = "wf"
        self.sessions = {}
        self.rules = {}
        self.sent_messages = []
        self.output_directory = str(tmp_path / "out")
        self.input_directory = str(tmp_path / "in")
        self.nodes = {
            "ad_studio/AdBrandBrief": {"python_class": AdBrandBrief},
            "ad_studio/AdProductImage": {"python_class": AdProductImage},
            "ad_studio/AdCreative": {"python_class": AdCreative},
            "ad_studio/AdFrame916": {"python_class": AdFrame916},
        }

    async def send_json(self, event, data, sid=None):
        self.sent_messages.append(data)


def test_parallel_executor_runs_creatives(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    product = _png(tmp_path / "product.png")
    prompt = {
        "1": {
            "type": "ad_studio/AdProductImage",
            "name": "PRODUCT IMAGE",
            "inputs": {"image_path": str(product)},
        },
        "2": {
            "type": "ad_studio/AdBrandBrief",
            "name": "BRAND WEBSITE + PRODUCT NAME",
            "inputs": {"website_url": "", "product_name": "Luma Serum"},
        },
    }
    for index, style_id in enumerate(
        ("claymation", "fake_tweet", "story_hook_916"), start=3
    ):
        prompt[str(index)] = {
            "type": "ad_studio/AdCreative",
            "name": style_id,
            "inputs": {
                "brand_brief": {"originId": "2"},
                "product_image": {"originId": "1"},
                "style_id": style_id,
                "aspect": "style",
                "variation": "parallel-take",
            },
        }

    server = _ExecServer(tmp_path)
    executor = GraphExecutor(server)
    graph = executor.prompt_to_graph(prompt)
    results = asyncio.run(
        executor.run_parallel(
            graph,
            {
                "prompt_id": "p",
                "client_id": "ad",
                "workflow_id": "wf",
                "number": 1,
            },
        )
    )
    assert results["3"].values["style_id"] == "claymation"
    assert results["4"].values["style_id"] == "fake_tweet"
    assert results["5"].values["aspect"] == "9:16"
    assert all(results[str(index)].values["placeholder"] for index in (3, 4, 5))
    assert server.sent_messages


def _http_server(tmp_path, loop):
    args = Namespace(
        enable_cors_header="*",
        enable_smart_cache=False,
        inspection_delay=0,
        enable_parallel_execution=False,
        max_parallel_nodes=2,
        max_upload_size=20,
        output_directory=str(tmp_path / "out"),
        input_directory=str(tmp_path / "in"),
    )
    server = Server(loop=loop, args=args)
    server.load_extensions()
    server.add_routes()
    return server


def _run_http(tmp_path, scenario):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    server = _http_server(tmp_path, loop)
    try:
        loop.run_until_complete(scenario(server))
    finally:
        loop.close()


def test_routes_serve_placeholder_upload_and_preview(tmp_path):
    async def go(server):
        client = TestClient(TestServer(server.app))
        await client.start_server()
        try:
            styles = await client.get("/ad-studio/styles")
            assert styles.status == 200
            body = await styles.json()
            assert len(body["styles"]) == 40

            placeholder = await client.get("/ad-studio/placeholders/claymation.png")
            assert placeholder.status == 200
            assert (await placeholder.read()).startswith(b"\x89PNG")

            preview = await client.get("/ad-studio/preview")
            assert preview.status == 200
            html = await preview.text()
            assert "litegraph.js" in html

            client_js = await client.get("/ad-studio/client.js")
            assert client_js.status == 200
            script = await client_js.text()
            assert "ad_studio/AdCreative" in script
            assert "KEEP" in script
            assert "[]/*__AD_STUDIO_STYLES__*/" not in script
            assert "claymation" in script

            form = aiohttp_form()
            upload = await client.post("/ad-studio/upload", data=form)
            assert upload.status == 200
            uploaded = await upload.json()
            assert uploaded["url"].startswith("/ad-studio/inputs/")
            fetched = await client.get(uploaded["url"])
            assert fetched.status == 200
        finally:
            await client.close()

    _run_http(tmp_path, go)


def aiohttp_form():
    import aiohttp

    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (255, 0, 0)).save(buffer, format="PNG")
    buffer.seek(0)
    form = aiohttp.FormData()
    form.add_field(
        "image",
        buffer,
        filename="bottle.png",
        content_type="image/png",
    )
    return form


def test_upload_rejects_non_images(tmp_path):
    async def go(server):
        client = TestClient(TestServer(server.app))
        await client.start_server()
        try:
            import aiohttp

            form = aiohttp.FormData()
            form.add_field(
                "image",
                io.BytesIO(b"not an image"),
                filename="notes.txt",
                content_type="text/plain",
            )
            response = await client.post("/ad-studio/upload", data=form)
            assert response.status == 400
        finally:
            await client.close()

    _run_http(tmp_path, go)
