"""Ad Studio nodes.

Phase 2 (not in this extension) can assemble TikToks from these results.
Each creative already returns ``prompt``, ``image_path``, ``width``,
``height``, and ``aspect`` so a later ffmpeg step does not need a new schema.
"""

import json
import os

from . import imaging, paths
from .brand import build_brief, default_extractor
from .prompts import compose_prompt, format_template, refine_prompt
from .styles import get_style, load_styles, style_ids

version = "1.0.0"

_CREATIVE_RETURN = {
    "kind": "*",
    "name": "ad",
    "cacheable": False,
}


def _input_value(node_inputs, group, name, default=None):
    return node_inputs.get(group, {}).get(name, {}).get("values", default)


def _server_from(node):
    memory = getattr(node, "_memory", None) or {}
    return memory.get("server")


def _coerce_brief(value):
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {"product_name": text, "brand_name": text}
        return parsed if isinstance(parsed, dict) else {}
    if isinstance(value, dict):
        return value
    return {}


def parse_favorites(value):
    if not value:
        return []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [value]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
        if isinstance(parsed, dict):
            return [parsed]
    return []


def _truthy(value):
    return str(value or "").strip().lower() in ("yes", "true", "1", "y")


def _resolve_aspect(style, choice):
    choice = str(choice or "style").strip() or "style"
    if choice in ("1:1", "9:16"):
        return choice
    return (style or {}).get("aspect") or "1:1"


class AdBrandBrief:
    CATEGORY = "ad_studio"
    SUBCATEGORY = "inputs"
    DESCRIPTION = (
        "Fetches a brand website and extracts a brief: name, tone, colors, "
        "claims, and audience. Without OPENAI_API_KEY this uses a heuristic."
    )

    INPUT = {
        "required_inputs": {
            "website_url": {
                "kind": "string",
                "name": "website_url",
                "widget": {
                    "kind": "string",
                    "name": "website_url",
                    "default": "https://example.com",
                },
            },
            "product_name": {
                "kind": "string",
                "name": "product_name",
                "widget": {
                    "kind": "string",
                    "name": "product_name",
                    "default": "Luma Serum",
                },
            },
        },
        "optional_inputs": {
            "extra_notes": {
                "kind": "*",
                "name": "extra_notes",
                "widget": {"kind": "string", "name": "extra_notes", "default": ""},
            }
        },
    }
    OUTPUT = {"kind": "*", "name": "brand_brief", "cacheable": False}

    extractor_factory = staticmethod(default_extractor)

    def evaluate(self, node_inputs):
        url = str(
            _input_value(node_inputs, "required_inputs", "website_url", "") or ""
        ).strip()
        product_name = str(
            _input_value(node_inputs, "required_inputs", "product_name", "") or ""
        ).strip()
        notes = str(
            _input_value(node_inputs, "optional_inputs", "extra_notes", "") or ""
        ).strip()
        extractor = type(self).extractor_factory()
        brief = build_brief(product_name, url, extractor=extractor)
        if notes:
            brief["extra_notes"] = notes
        return brief


class AdProductImage:
    CATEGORY = "ad_studio"
    SUBCATEGORY = "inputs"
    DESCRIPTION = (
        "Product photo. Paste a path or URL, or upload from the node. "
        "The creative nodes use this file as the image reference."
    )

    INPUT = {
        "required_inputs": {
            "image_path": {
                "kind": "string",
                "name": "image_path",
                "widget": {
                    "kind": "string",
                    "name": "image_path",
                    "default": "/ad-studio/placeholders/product.png",
                },
            }
        }
    }
    OUTPUT = {"kind": "*", "name": "product_image", "cacheable": True}

    def evaluate(self, node_inputs):
        raw = _input_value(node_inputs, "required_inputs", "image_path", "")
        server = _server_from(self)
        resolved = imaging.resolve_image_reference(raw, server=server)
        if not resolved or not os.path.isfile(resolved):
            raise RuntimeError(
                "Product image not found. Upload a photo or set a file path, "
                "http(s) URL, or /ad-studio/placeholders/product.png."
            )
        return {
            "image_path": resolved,
            "image_url": imaging.public_url_for_path(resolved, server)
            or str(raw or ""),
            "filename": os.path.basename(resolved),
        }


class AdCreative:
    CATEGORY = "ad_studio"
    SUBCATEGORY = "generate"
    DESCRIPTION = (
        "Writes one ad prompt from a style, the brand brief, and any favorited "
        "creatives, then generates a still with the product photo as reference."
    )

    INPUT = {
        "required_inputs": {
            "brand_brief": {"kind": "brand_brief", "name": "brand_brief"},
            "product_image": {"kind": "product_image", "name": "product_image"},
        },
        "optional_inputs": {
            "style_id": {
                "kind": "*",
                "name": "style_id",
                "widget": {
                    "kind": "string",
                    "name": "style_id",
                    "default": "claymation",
                },
            },
            "aspect": {
                "kind": "*",
                "name": "aspect",
                "widget": {"kind": "string", "name": "aspect", "default": "style"},
            },
            "refine_prompt": {
                "kind": "*",
                "name": "refine_prompt",
                "widget": {"kind": "string", "name": "refine_prompt", "default": "no"},
            },
            "favorites_json": {
                "kind": "*",
                "name": "favorites_json",
                "widget": {"kind": "string", "name": "favorites_json", "default": "[]"},
            },
            "variation": {
                "kind": "*",
                "name": "variation",
                "widget": {"kind": "string", "name": "variation", "default": ""},
            },
        },
    }
    OUTPUT = dict(_CREATIVE_RETURN)

    image_editor_factory = staticmethod(imaging.default_image_editor)

    def evaluate(self, node_inputs):
        brief = _coerce_brief(
            _input_value(node_inputs, "required_inputs", "brand_brief", {})
        )
        product_value = _input_value(
            node_inputs, "required_inputs", "product_image", ""
        )
        style_id = (
            _input_value(node_inputs, "optional_inputs", "style_id", "") or "claymation"
        )
        aspect = _resolve_aspect(
            get_style(style_id),
            _input_value(node_inputs, "optional_inputs", "aspect", "style"),
        )
        style = get_style(style_id) or get_style(style_ids()[0])
        favorites = parse_favorites(
            _input_value(node_inputs, "optional_inputs", "favorites_json", "[]")
        )
        variation = str(
            _input_value(node_inputs, "optional_inputs", "variation", "") or ""
        )
        prompt = compose_prompt(style, brief, favorites=favorites, variation=variation)
        refined = False
        if _truthy(_input_value(node_inputs, "optional_inputs", "refine_prompt", "no")):
            try:
                prompt = refine_prompt(prompt)
                refined = True
            except Exception as exc:
                prompt = prompt + f"\n(Prompt refine skipped: {exc})"

        server = _server_from(self)
        product_path = imaging.resolve_image_reference(product_value, server=server)
        if not product_path or not os.path.isfile(product_path):
            raise RuntimeError(
                "Ad Creative needs a product image from the Product Image node."
            )

        editor = type(self).image_editor_factory()
        model_name = os.environ.get("AD_STUDIO_IMAGE_MODEL") or "gpt-image-2"
        references = [product_path] + imaging.favorite_image_paths(
            favorites, server=server
        )
        placeholder = editor is None
        if placeholder:
            raw = imaging.render_placeholder(style, brief, aspect=aspect)
            model_label = "placeholder"
        else:
            raw = editor.edit(
                prompt=prompt,
                image_paths=references,
                size=imaging.api_size(aspect),
                model=model_name,
            )
            model_label = model_name

        width, height = imaging.output_size(aspect)
        png = imaging.frame_image(raw, width, height, fit="cover")
        image_path, image_url = imaging.save_png(png, server=server, prefix=style["id"])
        headline = ""
        if style.get("headline"):
            headline = format_template(style.get("headline"), brief)
        return {
            "prompt": prompt,
            "style_id": style["id"],
            "style_name": style["name"],
            "headline": headline,
            "image_path": image_path,
            "image_url": image_url,
            "width": width,
            "height": height,
            "aspect": aspect,
            "model": model_label,
            "placeholder": placeholder,
            "refined": refined,
            "reference_count": len(references),
            "favorite_count": len(favorites),
        }


class AdFrame916:
    CATEGORY = "ad_studio"
    SUBCATEGORY = "generate"
    DESCRIPTION = (
        "Converts an existing creative to a 1080x1920 vertical still by "
        "cover-cropping or padding. Does not call the image model."
    )

    INPUT = {
        "required_inputs": {
            "image": {"kind": "ad_image", "name": "image"},
        },
        "optional_inputs": {
            "fit": {
                "kind": "*",
                "name": "fit",
                "widget": {"kind": "string", "name": "fit", "default": "cover"},
            }
        },
    }
    OUTPUT = {
        "kind": "*",
        "name": "ad",
        "cacheable": False,
    }

    def evaluate(self, node_inputs):
        source = _input_value(node_inputs, "required_inputs", "image", "")
        fit = str(
            _input_value(node_inputs, "optional_inputs", "fit", "cover") or "cover"
        ).strip()
        if fit not in ("cover", "pad"):
            fit = "cover"
        server = _server_from(self)
        path = imaging.resolve_image_reference(source, server=server)
        if not path or not os.path.isfile(path):
            raise RuntimeError("9:16 frame needs an image path from an Ad Creative.")
        with open(path, "rb") as handle:
            raw = handle.read()
        png = imaging.frame_image(raw, 1080, 1920, fit=fit)
        image_path, image_url = imaging.save_png(png, server=server, prefix="frame-916")
        source_prompt = ""
        if isinstance(source, dict):
            source_prompt = str(source.get("prompt") or "")
        return {
            "prompt": source_prompt,
            "style_id": "frame_916",
            "style_name": "9:16 conversion",
            "headline": "9:16",
            "image_path": image_path,
            "image_url": image_url,
            "width": 1080,
            "height": 1920,
            "aspect": "9:16",
            "model": "frame",
            "placeholder": bool(isinstance(source, dict) and source.get("placeholder")),
            "fit": fit,
            "source_path": path,
        }


def _node(python_class, javascript_class_name, display_name):
    return {
        "python_class": python_class,
        "javascript_class_name": javascript_class_name,
        "display_name": display_name,
    }


EXTENSION_MAPPINGS = {
    "name": "ad_studio",
    "version": version,
    "description": "Generate a grid of static ad creatives from a brand site and a product photo.",
    "javascript_class_name": "ad_studio",
    "nodes": {
        "ad_studio/AdBrandBrief": _node(
            AdBrandBrief, "ad_studio/AdBrandBrief", "BRAND WEBSITE + PRODUCT NAME"
        ),
        "ad_studio/AdProductImage": _node(
            AdProductImage, "ad_studio/AdProductImage", "PRODUCT IMAGE"
        ),
        "ad_studio/AdCreative": _node(
            AdCreative, "ad_studio/AdCreative", "Ad Creative"
        ),
        "ad_studio/AdFrame916": _node(AdFrame916, "ad_studio/AdFrame916", "TO 9:16"),
    },
    "rules": {},
}


def register(server):
    """Serve uploads, generated PNGs, and the style catalog. Inject styles into web.js."""
    from .routes import register_routes

    register_routes(server)
    extension = server.extensions.get("ad_studio")
    if not extension:
        return
    token = "[]/*__AD_STUDIO_STYLES__*/"
    javascript = extension.get("javascript") or ""
    if token in javascript:
        extension["javascript"] = javascript.replace(
            token, json.dumps(load_styles()), 1
        )
    # Touch the directories so a fresh server can accept uploads immediately.
    paths.output_dir(server)
    paths.input_dir(server)
