"""Caption and hashtag variants for one creative.

Uses ``AD_STUDIO_TEXT_MODEL`` when ``OPENAI_API_KEY`` is set and the node
asks for the model. Otherwise a deterministic heuristic writes the lines.
"""

import json
import os
import re

_HOOKS = (
    "Stop scrolling.",
    "We almost didn't post this.",
    "The product is the whole ad.",
    "Unpopular opinion:",
    "This one earned the favorite.",
    "No jingle. Just the bottle.",
    "Read the caption, then look again.",
    "Posted it before we talked ourselves out of it.",
)

_HASHTAGS = (
    "#ad",
    "#new",
    "#launch",
    "#behindtheshot",
    "#productphoto",
    "#smallbatch",
    "#dailypost",
    "#creative",
)


def generate_for_creatives(creatives, count=3, tone="", instructions="", use_model="auto", brief=None):
    count = _count(count)
    variants_by_index = []
    model_label = "heuristic"
    for index, creative in enumerate(creatives):
        text, label = generate_captions(
            creative,
            count=count,
            tone=tone,
            instructions=instructions,
            use_model=use_model,
            brief=brief,
            index=index,
        )
        if label != "heuristic":
            model_label = label
        variants_by_index.append({"creative_index": index, "variants": text})
    return {"captions": variants_by_index, "model": model_label, "count": count}


def generate_captions(creative, count=3, tone="", instructions="", use_model="auto", brief=None, index=0):
    count = _count(count)
    mode = str(use_model or "auto").strip().lower()
    if mode not in ("auto", "yes", "no"):
        mode = "auto"
    if mode != "no" and os.environ.get("OPENAI_API_KEY"):
        try:
            text = _from_model(
                creative,
                count=count,
                tone=tone,
                instructions=instructions,
                brief=brief,
            )
            if len(text) >= count:
                model = os.environ.get("AD_STUDIO_TEXT_MODEL") or "gpt-4.1-mini"
                return text[:count], model
        except Exception:
            if mode == "yes":
                raise
    return _heuristic(creative, count, tone, instructions, brief, index), "heuristic"


def _from_model(creative, count, tone, instructions, brief):
    raw = _call_text_model(
        _model_prompt(creative, count, tone, instructions, brief)
    )
    return _parse_model_lines(raw, count)


def _call_text_model(prompt):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    model = os.environ.get("AD_STUDIO_TEXT_MODEL") or "gpt-4.1-mini"
    try:
        from server.domain.utilities.httpx_proxies_compat import (
            apply_httpx_proxies_compat,
        )

        apply_httpx_proxies_compat()
    except Exception:
        pass
    from openai import OpenAI

    client = OpenAI(api_key=api_key, timeout=60)
    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "user",
                "content": [{"type": "input_text", "text": prompt}],
            }
        ],
    )
    return _response_text(response)


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


def _model_prompt(creative, count, tone, instructions, brief):
    product = _product_name(creative, brief)
    claim = _claim(creative, brief)
    style = (creative or {}).get("style_name") or (creative or {}).get("style_id") or "ad"
    tone_text = tone or (brief or {}).get("tone") or "direct"
    extra = instructions.strip() if instructions else ""
    return (
        "Write "
        + str(count)
        + " different social captions for one ad creative. "
        "Return a JSON array of strings and nothing else. "
        "Each caption is one or two sentences plus 3 to 5 hashtags. "
        "Do not invent claims that are not provided. "
        f"Product: {product}. Style: {style}. Tone: {tone_text}. "
        f"Claim you may echo: {claim or 'none'}. "
        f"Extra instructions: {extra or 'none'}."
    )


def _parse_model_lines(raw, count):
    text = str(raw or "").strip()
    match = re.search(r"\[[\s\S]*\]", text)
    if not match:
        raise RuntimeError("caption model did not return a JSON array")
    parsed = json.loads(match.group(0))
    if not isinstance(parsed, list):
        raise RuntimeError("caption model did not return a JSON array")
    lines = []
    for item in parsed:
        line = str(item or "").strip()
        if line:
            lines.append(line)
    if len(lines) < count:
        raise RuntimeError("caption model returned too few lines")
    return lines


def _heuristic(creative, count, tone, instructions, brief, index):
    product = _product_name(creative, brief)
    claim = _claim(creative, brief)
    style = (creative or {}).get("style_name") or "this ad"
    tone_text = (tone or (brief or {}).get("tone") or "direct").strip()
    note = (instructions or "").strip()
    lines = []
    for offset in range(count):
        hook = _HOOKS[(index + offset) % len(_HOOKS)]
        tags = _hashtags(product, offset)
        claim_bit = f" {claim}." if claim else ""
        extra = f" {note}" if note else ""
        lines.append(
            f"{hook} {product} — {style}, {tone_text}.{claim_bit}{extra} {tags}".replace(
                "  ", " "
            ).strip()
        )
    return lines


def _hashtags(product, offset):
    slug = re.sub(r"[^A-Za-z0-9]", "", product or "")
    tags = []
    if slug:
        tags.append("#" + slug[:24])
    for shift in range(4):
        tags.append(_HASHTAGS[(offset + shift) % len(_HASHTAGS)])
    # unique, keep order
    seen = []
    for tag in tags:
        if tag not in seen:
            seen.append(tag)
    return " ".join(seen[:5])


def _product_name(creative, brief):
    brief = brief or {}
    creative = creative or {}
    for value in (
        creative.get("product_name"),
        brief.get("product_name"),
        creative.get("headline"),
        creative.get("style_name"),
    ):
        text = str(value or "").strip()
        if text:
            return text
    return "the product"


def _claim(creative, brief):
    brief = brief or {}
    claims = brief.get("claims") or (creative or {}).get("claims") or []
    if isinstance(claims, (list, tuple)) and claims:
        return str(claims[0])
    if isinstance(claims, str):
        return claims.strip()
    return ""


def _count(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 3
    return max(1, min(number, 12))
