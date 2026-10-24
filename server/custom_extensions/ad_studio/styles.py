"""Load the Ad Studio style library."""

from .catalog import STYLES


def load_styles():
    """Return a copy of every style template."""
    return [dict(style) for style in STYLES]


def style_ids():
    return [style["id"] for style in STYLES]


def get_style(style_id):
    wanted = str(style_id or "").strip()
    for style in STYLES:
        if style["id"] == wanted:
            return dict(style)
    return None
