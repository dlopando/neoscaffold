"""Platform adapter registry."""

from .facebook import FacebookAdapter
from .instagram import InstagramAdapter
from .linkedin import LinkedInAdapter
from .tiktok import TikTokAdapter
from .x import XAdapter
from .youtube import YouTubeAdapter

ADAPTERS = {
    "tiktok": TikTokAdapter,
    "instagram": InstagramAdapter,
    "facebook": FacebookAdapter,
    "x": XAdapter,
    "youtube": YouTubeAdapter,
    "linkedin": LinkedInAdapter,
}


def platform_names():
    return list(ADAPTERS)


def get_adapter(platform, transport=None, env=None):
    key = str(platform or "").strip().lower()
    cls = ADAPTERS.get(key)
    if cls is None:
        raise KeyError("unknown platform " + key)
    return cls(transport=transport, env=env)


def catalog(env=None):
    return [get_adapter(name, env=env).describe() for name in platform_names()]
