"""Copy a local creative into the public media folder when a base URL is set."""

import os
import shutil

from . import paths
from .constraints import media_kind


def media_source_from_creative(creative, server=None):
    """Build a dict the adapters understand. Does not read the file."""
    creative = creative or {}
    kind = media_kind(creative)
    path = str(creative.get("video_path") or creative.get("image_path") or "")
    url = str(creative.get("image_url") or creative.get("video_url") or "")
    filename = os.path.basename(path) if path else ""
    if path and os.path.isfile(path):
        filename = _publish_copy(path, server) or filename
        public = os.environ.get("SOCIAL_STUDIO_PUBLIC_MEDIA_BASE", "").rstrip("/")
        if public and filename and not url.startswith("https://"):
            url = public + "/social-studio/media/" + filename
    mime = _mime(path, kind)
    return {
        "path": path,
        "url": url,
        "kind": kind,
        "mime": mime,
        "filename": filename,
        "width": int(creative.get("width") or 0),
        "height": int(creative.get("height") or 0),
        "aspect": str(creative.get("aspect") or ""),
    }


def _publish_copy(path, server):
    """Copy into the media dir unless the file is already there. Returns basename."""
    directory = os.path.abspath(paths.media_dir(server))
    source = os.path.abspath(path)
    if os.path.commonpath([directory, source]) == directory:
        return os.path.basename(source)
    name = paths.safe_filename(os.path.basename(source))
    target = os.path.join(directory, name)
    if not os.path.isfile(target):
        shutil.copyfile(source, target)
    return name


def _mime(path, kind):
    extension = os.path.splitext(path)[1].lower()
    if extension == ".png":
        return "image/png"
    if extension in (".jpg", ".jpeg"):
        return "image/jpeg"
    if extension == ".webp":
        return "image/webp"
    if extension == ".mov":
        return "video/quicktime"
    if extension == ".webm":
        return "video/webm"
    if kind == "video":
        return "video/mp4"
    return "image/jpeg"
