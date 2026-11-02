"""Per-platform media constraints used by the distributor.

These are publishing guards, not a guarantee that a platform will accept
every file that passes. Official limits change; the README lists the
sources the numbers came from.
"""

import os

# aspect label -> width/height ratio
ASPECTS = {
    "1:1": 1.0,
    "4:5": 0.8,
    "9:16": 9 / 16,
    "16:9": 16 / 9,
    "1.91:1": 1.91,
}

# Allowed aspect labels and max bytes. ``video_images`` is False when the
# platform cannot publish a still through the API this extension calls.
LIMITS = {
    "tiktok": {
        "images": True,
        "videos": True,
        "image_aspects": ("1:1", "9:16", "4:5"),
        "video_aspects": ("9:16", "1:1"),
        "image_max_bytes": 20 * 1024 * 1024,
        "video_max_bytes": 4 * 1024 * 1024 * 1024,
        "caption_max": 2200,
        "needs_public_url_for_images": True,
    },
    "instagram": {
        "images": True,
        "videos": True,
        "image_aspects": ("1:1", "4:5", "9:16"),
        "video_aspects": ("9:16", "1:1", "4:5"),
        "image_max_bytes": 8 * 1024 * 1024,
        "video_max_bytes": 1024 * 1024 * 1024,
        "caption_max": 2200,
        "needs_public_url_for_images": True,
    },
    "facebook": {
        "images": True,
        "videos": True,
        "image_aspects": ("1:1", "4:5", "9:16", "16:9", "1.91:1"),
        "video_aspects": ("9:16", "1:1", "16:9", "4:5"),
        "image_max_bytes": 10 * 1024 * 1024,
        "video_max_bytes": 1024 * 1024 * 1024,
        "caption_max": 5000,
        "needs_public_url_for_images": False,
    },
    "x": {
        "images": True,
        "videos": True,
        "image_aspects": ("1:1", "4:5", "9:16", "16:9", "1.91:1"),
        "video_aspects": ("9:16", "1:1", "16:9"),
        "image_max_bytes": 5 * 1024 * 1024,
        "video_max_bytes": 512 * 1024 * 1024,
        "caption_max": 280,
        "needs_public_url_for_images": False,
    },
    "youtube": {
        "images": False,
        "videos": True,
        "image_aspects": (),
        "video_aspects": ("9:16", "16:9", "1:1"),
        "image_max_bytes": 0,
        "video_max_bytes": 256 * 1024 * 1024 * 1024,
        "caption_max": 5000,
        "title_max": 100,
        "needs_public_url_for_images": False,
    },
    "linkedin": {
        "images": True,
        "videos": False,
        "image_aspects": ("1:1", "4:5", "9:16", "16:9", "1.91:1"),
        "video_aspects": (),
        "image_max_bytes": 10 * 1024 * 1024,
        "video_max_bytes": 0,
        "caption_max": 3000,
        "needs_public_url_for_images": False,
    },
}


def media_kind(creative):
    explicit = str((creative or {}).get("media_kind") or "").strip().lower()
    if explicit in ("image", "video"):
        return explicit
    path = str((creative or {}).get("image_path") or (creative or {}).get("video_path") or "")
    extension = os.path.splitext(path)[1].lower()
    if extension in (".mp4", ".mov", ".webm", ".m4v"):
        return "video"
    if (creative or {}).get("video_path"):
        return "video"
    return "image"


def aspect_label(creative):
    label = str((creative or {}).get("aspect") or "").strip()
    if label in ASPECTS:
        return label
    width = _number((creative or {}).get("width"))
    height = _number((creative or {}).get("height"))
    if width and height:
        return _closest_aspect(width / height)
    return ""


def file_size(creative):
    path = _media_path(creative)
    if path and os.path.isfile(path):
        return os.path.getsize(path)
    size = (creative or {}).get("size_bytes")
    if size is None:
        return None
    try:
        return int(size)
    except (TypeError, ValueError):
        return None


def check_creative(platform, creative):
    """Return (compatible, warnings, skip_reason)."""
    limits = LIMITS.get(platform)
    if not limits:
        return False, [], f"unknown platform {platform}"
    kind = media_kind(creative)
    warnings = []
    if kind == "image" and not limits["images"]:
        return (
            False,
            warnings,
            f"{platform} does not publish still images through this adapter",
        )
    if kind == "video" and not limits["videos"]:
        return (
            False,
            warnings,
            f"{platform} video publishing is not implemented",
        )
    aspect = aspect_label(creative)
    allowed = limits["image_aspects"] if kind == "image" else limits["video_aspects"]
    if aspect and allowed and aspect not in allowed:
        return (
            False,
            warnings,
            f"{platform} does not accept {kind} aspect {aspect}",
        )
    if not aspect:
        warnings.append(f"No aspect ratio on the creative; {platform} may crop it.")
    size = file_size(creative)
    maximum = limits["image_max_bytes"] if kind == "image" else limits["video_max_bytes"]
    if size is not None and maximum and size > maximum:
        return (
            False,
            warnings,
            f"{platform} {kind} is {size} bytes; limit is {maximum}",
        )
    if size is None:
        warnings.append("Media file size was not checked because the file is not on disk yet.")
    if kind == "image" and limits["needs_public_url_for_images"]:
        url = str((creative or {}).get("image_url") or "")
        if not url.startswith("https://") and not os.environ.get("SOCIAL_STUDIO_PUBLIC_MEDIA_BASE"):
            warnings.append(
                f"{platform} pulls images from a public HTTPS URL. "
                "Set SOCIAL_STUDIO_PUBLIC_MEDIA_BASE or an https image_url before a live post."
            )
    if kind == "video" and platform == "youtube" and aspect and aspect != "9:16":
        warnings.append("YouTube Shorts should be vertical 9:16. This video is " + aspect + ".")
    return True, warnings, ""


def trim_caption(platform, caption):
    limits = LIMITS.get(platform) or {}
    maximum = int(limits.get("caption_max") or 2200)
    text = str(caption or "").strip()
    if len(text) <= maximum:
        return text, []
    trimmed = text[: maximum - 1].rstrip() + "…"
    return trimmed, [f"Caption trimmed to {maximum} characters for {platform}."]


def _media_path(creative):
    creative = creative or {}
    return str(creative.get("video_path") or creative.get("image_path") or "")


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    return number


def _closest_aspect(ratio):
    best = ""
    best_delta = 999
    for label, value in ASPECTS.items():
        delta = abs(ratio - value)
        if delta < best_delta:
            best = label
            best_delta = delta
    if best_delta > 0.08:
        return ""
    return best
