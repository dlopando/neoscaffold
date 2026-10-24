"""Compose a single still-ad prompt from a style, a brand brief, and favorites."""

import os
import random

SAMPLE_BRIEF = {
    "brand_name": "Luma",
    "product_name": "Luma Serum",
    "tagline": "Glow, without the guesswork",
    "tone": "confident, witty, a little contrarian",
    "colors": ["#F4C7C3", "#1A1A1A", "#F7F4EF"],
    "claims": [
        "97% saw brighter skin in 14 days",
        "fragrance free",
        "dermatologist tested",
    ],
    "audience": "skeptical skincare shoppers 25-40",
    "category": "facial serum",
    "differentiators": ["one-pump dose", "glass dropper bottle"],
    "do_not_say": ["cure", "medical treatment"],
    "source_url": "https://example.com",
    "extractor": "sample",
}

_TAKES = (
    "tighter crop, more negative space",
    "louder type, quieter background",
    "warmer light, softer shadow",
    "stranger angle, same product",
    "fewer words, bigger product",
    "a joke in the subline",
    "more tactile texture",
    "calmer color, sharper headline",
)


class _SafeDict(dict):
    def __missing__(self, key):
        return ""


def _join(value):
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value if item)
    if value is None:
        return ""
    return str(value)


def brief_fields(brief):
    """Flatten a brand brief into format fields."""
    data = brief if isinstance(brief, dict) else {}
    return _SafeDict(
        {
            "brand_name": data.get("brand_name") or "the brand",
            "product_name": data.get("product_name") or "the product",
            "tagline": data.get("tagline") or "",
            "tone": data.get("tone") or "direct",
            "colors": _join(data.get("colors")) or "the brand colors",
            "claims": _join(data.get("claims")) or "only claims present in the brief",
            "audience": data.get("audience") or "the customer",
            "category": data.get("category") or "the product category",
            "differentiators": _join(data.get("differentiators")) or "",
            "do_not_say": _join(data.get("do_not_say")) or "",
        }
    )


def format_template(template, brief):
    return str(template or "").format_map(brief_fields(brief))


def random_take():
    return random.choice(_TAKES)


def favorites_note(favorites):
    if not favorites:
        return "No favorite ads yet. Invent a fresh execution of this style."
    lines = [
        "Riff on these favorites. Do not copy them. Steal the energy and make a new ad."
    ]
    for index, favorite in enumerate(list(favorites)[:5], start=1):
        if not isinstance(favorite, dict):
            continue
        name = favorite.get("style_name") or favorite.get("style_id") or "favorite"
        prompt = str(favorite.get("prompt") or "").strip().replace("\n", " ")
        if len(prompt) > 400:
            prompt = prompt[:400].rstrip() + "..."
        lines.append(f"{index}. {name}: {prompt}")
    return "\n".join(lines)


def compose_prompt(style, brief, favorites=None, variation=""):
    """Build the image prompt for one creative.

    The result is deterministic when ``variation`` is provided. An empty
    variation picks a fresh take so a re-run does not repeat the last prompt.
    """
    style = style or {}
    fields = brief_fields(brief)
    headline = format_template(style.get("headline") or "", brief).strip()
    direction = format_template(style.get("template") or "", brief).strip()
    take = (
        variation.strip()
        if isinstance(variation, str) and variation.strip()
        else random_take()
    )
    banned = fields["do_not_say"]

    parts = [
        "Create one static advertisement still, not a collage and not a video frame sequence.",
        f"Style: {style.get('name') or style.get('id') or 'ad'}.",
        direction,
        (
            "The attached reference photo is the real product. Keep its shape, "
            "label, logo, and colors recognizable. Do not redesign the packaging."
        ),
        f"Brand: {fields['brand_name']}. Product: {fields['product_name']}.",
        f"Tone: {fields['tone']}. Audience: {fields['audience']}.",
    ]
    if headline:
        parts.append(f'Render this headline spelled exactly: "{headline}".')
    else:
        parts.append(
            "Any interface text should be short, legible, and in the brand tone."
        )
    if banned:
        parts.append(f"Do not say: {banned}.")
    parts.append(favorites_note(favorites))
    parts.append(f"Fresh take: {take}.")
    parts.append(
        "Model label for the workflow is GPT IMAGE 2. Do not print that label unless the style asks for it."
    )
    prompt = "\n".join(part for part in parts if part)
    if len(prompt) > 4000:
        prompt = prompt[:4000]
    return prompt


def _response_text(response):
    text = getattr(response, "output_text", None)
    if text:
        return text
    chunks = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            value = getattr(content, "text", None)
            if value:
                chunks.append(value)
    return "\n".join(chunks)


def refine_prompt(prompt, api_key=None, model=None, timeout=60):
    """Optional LLM pass that rewrites a composed prompt. Raises if no key."""
    api_key = os.environ.get("OPENAI_API_KEY") if api_key is None else api_key
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    model = model or os.environ.get("AD_STUDIO_TEXT_MODEL") or "gpt-4.1-mini"
    try:
        from server.domain.utilities.httpx_proxies_compat import (
            apply_httpx_proxies_compat,
        )

        apply_httpx_proxies_compat()
    except Exception:
        pass
    from openai import OpenAI

    client = OpenAI(api_key=api_key, timeout=timeout)
    instruction = (
        "Rewrite this advertisement image prompt so it is specific and visual. "
        "Keep every mandatory headline exactly. Keep the instruction to preserve "
        "the real product photo. Return only the prompt.\n\n" + prompt
    )
    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "user",
                "content": [{"type": "input_text", "text": instruction}],
            }
        ],
    )
    text = str(_response_text(response) or "").strip()
    if len(text) > 4000:
        text = text[:4000]
    return text or prompt
