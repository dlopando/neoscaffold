"""Save ad images, frame them, and call the OpenAI images edit API.

Generated pixels are written to disk. Node results carry a file path and an
HTTP URL, never base64, because workflow JSON stores ``properties.result``.
"""

import base64
import io
import os
import uuid
from urllib.parse import urlparse

import httpx
from PIL import Image, ImageDraw, ImageFont, ImageOps

from . import paths
from .prompts import SAMPLE_BRIEF, format_template
from .styles import get_style

SQUARE = (1024, 1024)
VERTICAL = (1080, 1920)
_API_SIZE = {"1:1": "1024x1024", "9:16": "1024x1536"}

_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


class MissingAPIKey(RuntimeError):
    pass


def _font(size):
    for candidate in _FONT_CANDIDATES:
        if os.path.isfile(candidate):
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def _hex_to_rgb(value, fallback=(26, 28, 34)):
    text = str(value or "").strip()
    if text.startswith("#") and len(text) == 7:
        try:
            return tuple(int(text[index : index + 2], 16) for index in (1, 3, 5))
        except ValueError:
            return fallback
    return fallback


def _wrap(draw, text, font, width):
    words = str(text or "").split()
    if not words:
        return []
    lines = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if draw.textlength(trial, font=font) <= width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def png_bytes(image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def open_png(data):
    return Image.open(io.BytesIO(data)).convert("RGBA")


def frame_image(data, width, height, fit="cover", pad_color=(17, 17, 17)):
    """Crop or pad image bytes to an exact pixel size. Returns PNG bytes."""
    image = Image.open(io.BytesIO(data)).convert("RGB")
    if fit == "pad":
        framed = ImageOps.contain(image, (width, height), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (width, height), pad_color)
        left = (width - framed.width) // 2
        top = (height - framed.height) // 2
        canvas.paste(framed, (left, top))
    else:
        framed = ImageOps.fit(
            image, (width, height), Image.Resampling.LANCZOS, centering=(0.5, 0.5)
        )
        canvas = framed
    return png_bytes(canvas)


def output_size(aspect):
    if aspect == "9:16":
        return VERTICAL
    return SQUARE


def api_size(aspect):
    return _API_SIZE.get(aspect, "1024x1024")


def render_placeholder(style, brief=None, aspect=None):
    """Draw a clearly labeled stand-in so the canvas can be reviewed without a key."""
    brief = brief or SAMPLE_BRIEF
    style = style or {
        "id": "ad",
        "name": "Ad",
        "color": "#8AB4FF",
        "headline": "",
        "aspect": "1:1",
    }
    aspect = aspect or style.get("aspect") or "1:1"
    width, height = output_size(aspect)
    # Keep preview files lighter than final delivery files. The label is the point.
    preview_width = 640 if aspect == "1:1" else 540
    preview_height = 640 if aspect == "1:1" else 960
    color = _hex_to_rgb(style.get("color"), (138, 180, 255))
    image = Image.new("RGB", (preview_width, preview_height), (18, 20, 26))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, preview_width, 18), fill=color)
    draw.rectangle(
        (0, preview_height - 86, preview_width, preview_height), fill=(40, 12, 16)
    )

    title_font = _font(36 if aspect == "1:1" else 32)
    body_font = _font(22)
    small_font = _font(16)
    headline = format_template(
        style.get("headline") or style.get("name") or "AD", brief
    )
    headline = headline.strip() or style.get("name") or "AD"
    draw.text((28, 40), headline[:42], font=title_font, fill=(245, 245, 245))
    lines = _wrap(
        draw,
        f"{style.get('name')}  ·  {brief.get('product_name', '')}",
        body_font,
        preview_width - 56,
    )
    top = 110
    for line in lines[:4]:
        draw.text((28, top), line, font=body_font, fill=(210, 214, 220))
        top += 30
    draw.text(
        (28, preview_height - 68), "PLACEHOLDER", font=title_font, fill=(255, 120, 120)
    )
    draw.text(
        (28, preview_height - 28),
        "NOT A MODEL IMAGE  ·  SET OPENAI_API_KEY",
        font=small_font,
        fill=(255, 190, 190),
    )
    draw.text((28, preview_height - 110), "GPT IMAGE 2", font=small_font, fill=color)
    return png_bytes(image)


def render_product_placeholder():
    """A fake product shot used by the example workflow."""
    image = Image.new("RGB", (640, 640), (244, 236, 230))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (230, 120, 410, 520),
        radius=40,
        fill=(255, 255, 255),
        outline=(30, 30, 30),
        width=4,
    )
    draw.rectangle((292, 70, 348, 140), fill=(30, 30, 30))
    draw.ellipse((300, 48, 340, 88), fill=(80, 80, 80))
    draw.rectangle((250, 250, 390, 360), fill=(244, 199, 195))
    font = _font(22)
    small = _font(16)
    draw.text((268, 280), "LUMA", font=font, fill=(26, 26, 26))
    draw.text((262, 312), "SERUM", font=font, fill=(26, 26, 26))
    draw.text((150, 560), "PLACEHOLDER PRODUCT", font=small, fill=(90, 40, 40))
    return png_bytes(image)


def ensure_placeholder(name, server=None, brief=None):
    """Write a placeholder PNG once and return its filesystem path."""
    filename = paths.safe_filename(name, default="ad") + ".png"
    path = paths.contained_file(paths.placeholder_dir(server), filename)
    if path and os.path.isfile(path):
        return path
    if name in ("product", "product.png"):
        data = render_product_placeholder()
    else:
        style = get_style(name) or {
            "id": name,
            "name": str(name or "Ad").replace("_", " ").title(),
            "aspect": "9:16" if str(name).endswith("916") else "1:1",
            "color": "#8AB4FF",
            "headline": "9:16" if "916" in str(name) else "",
        }
        data = render_placeholder(style, brief=brief, aspect=style.get("aspect"))
    with open(path, "wb") as handle:
        handle.write(data)
    return path


def save_png(data, server=None, prefix="ad"):
    filename = (
        f"{paths.safe_filename(prefix, default='ad')}-{uuid.uuid4().hex[:12]}.png"
    )
    path = os.path.join(paths.output_dir(server), filename)
    with open(path, "wb") as handle:
        handle.write(data)
    return path, f"/ad-studio/outputs/{filename}"


def public_url_for_path(path, server=None):
    if not path:
        return ""
    absolute = os.path.abspath(path)
    for directory, prefix in (
        (paths.output_dir(server), "/ad-studio/outputs"),
        (paths.placeholder_dir(server), "/ad-studio/placeholders"),
        (paths.input_dir(server), "/ad-studio/inputs"),
    ):
        directory = os.path.abspath(directory)
        if os.path.commonpath([directory, absolute]) == directory:
            name = os.path.basename(absolute)
            return f"{prefix}/{name}"
    return ""


def resolve_image_reference(value, server=None):
    """Turn a widget value, result dict, site path, or http URL into a local file."""
    if isinstance(value, dict):
        for key in ("image_path", "path"):
            candidate = value.get(key)
            if candidate and os.path.isfile(str(candidate)):
                return os.path.abspath(str(candidate))
        for key in ("image_url", "url"):
            if value.get(key):
                return resolve_image_reference(value.get(key), server=server)
        return ""

    text = str(value or "").strip()
    if not text:
        return ""
    if os.path.isfile(text):
        return os.path.abspath(text)

    if text.startswith("/ad-studio/placeholders/"):
        name = os.path.basename(text)
        style_id = name[:-4] if name.lower().endswith(".png") else name
        return ensure_placeholder(style_id, server=server)
    if text.startswith("/ad-studio/outputs/"):
        return (
            paths.contained_file(paths.output_dir(server), os.path.basename(text)) or ""
        )
    if text.startswith("/ad-studio/inputs/"):
        return (
            paths.contained_file(paths.input_dir(server), os.path.basename(text)) or ""
        )

    parsed = urlparse(text)
    if parsed.scheme in ("http", "https"):
        return _download_image(text, server=server)
    return ""


def _download_image(url, server=None):
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Could not download product image: {exc}") from exc
    content_type = response.headers.get("content-type", "")
    extension = ".png"
    if "jpeg" in content_type or "jpg" in content_type:
        extension = ".jpg"
    elif "webp" in content_type:
        extension = ".webp"
    filename = f"download-{uuid.uuid4().hex[:12]}{extension}"
    path = os.path.join(paths.input_dir(server), filename)
    with open(path, "wb") as handle:
        handle.write(response.content)
    return path


def decode_image_payload(payload):
    """Accept raw bytes, a data URL, base64, or an http URL."""
    if isinstance(payload, (bytes, bytearray)):
        return bytes(payload)
    if not isinstance(payload, str):
        raise RuntimeError("Image editor returned no image data")
    if payload.startswith("data:"):
        payload = payload.split(",", 1)[-1]
    if payload.startswith("http://") or payload.startswith("https://"):
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            response = client.get(payload)
            response.raise_for_status()
            return response.content
    return base64.b64decode(payload)


class OpenAIImageEditor:
    """images.edit wrapper. The product photo is the reference image."""

    def __init__(self, api_key=None, timeout=180):
        self.api_key = (
            api_key if api_key is not None else os.environ.get("OPENAI_API_KEY")
        )
        self.timeout = timeout

    def edit(self, prompt, image_paths, size, model):
        if not self.api_key:
            raise MissingAPIKey("OPENAI_API_KEY is not set")
        try:
            from server.domain.utilities.httpx_proxies_compat import (
                apply_httpx_proxies_compat,
            )

            apply_httpx_proxies_compat()
        except Exception:
            pass
        from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

        client = OpenAI(api_key=self.api_key, timeout=self.timeout)
        handles = [open(path, "rb") for path in image_paths]
        try:
            image_arg = handles[0] if len(handles) == 1 else handles
            try:
                response = client.images.edit(
                    model=model,
                    image=image_arg,
                    prompt=prompt,
                    size=size,
                    n=1,
                )
            except APITimeoutError as exc:
                raise RuntimeError(
                    f"OpenAI image edit timed out after {self.timeout:g} seconds"
                ) from exc
            except APIStatusError as exc:
                raise RuntimeError(
                    "OpenAI image edit failed with "
                    f"status {exc.status_code}: {exc.response.text}"
                ) from exc
            except APIConnectionError as exc:
                raise RuntimeError(
                    f"OpenAI image edit connection failed: {exc}"
                ) from exc
        finally:
            for handle in handles:
                handle.close()

        data = response.data[0]
        encoded = getattr(data, "b64_json", None) or getattr(data, "url", None)
        return decode_image_payload(encoded)


def default_image_editor():
    if not os.environ.get("OPENAI_API_KEY"):
        return None
    return OpenAIImageEditor()


def favorite_image_paths(favorites, server=None, limit=2):
    paths_found = []
    for favorite in favorites or []:
        if not isinstance(favorite, dict):
            continue
        try:
            resolved = resolve_image_reference(favorite, server=server)
        except Exception:
            resolved = ""
        if resolved and os.path.isfile(resolved):
            paths_found.append(resolved)
        if len(paths_found) >= limit:
            break
    return paths_found
