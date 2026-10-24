"""Fetch a product page and turn it into a structured brand brief."""

import json
import os
import re
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx

_HEX_COLOR = re.compile(r"#[0-9A-Fa-f]{6}")
_BRIEF_INSTRUCTION = """Extract a brand brief as a single JSON object.
Use only facts supported by the page text. Leave unknown strings empty and unknown lists empty.
Do not invent clinical claims, awards, or prices.

Keys:
- brand_name (string)
- product_name (string)
- tagline (string)
- tone (string, a few words)
- colors (array of hex colors if present, else words)
- claims (array of short factual claims)
- audience (string)
- category (string)
- differentiators (array of short strings)
- do_not_say (array of risky phrases to avoid)
- page_excerpt (string, one sentence)

Product name hint: {product_name}
Page URL: {url}

PAGE TEXT:
{page_text}
"""


class PageFetchError(RuntimeError):
    pass


class _PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.in_title = False
        self.title_parts = []
        self.parts = []
        self.meta_description = ""
        self.colors = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"):
            self.skip_depth += 1
        if tag == "title":
            self.in_title = True
        attr_map = {key.lower(): value or "" for key, value in attrs}
        if tag == "meta":
            name = (attr_map.get("name") or attr_map.get("property") or "").lower()
            if name in ("description", "og:description", "twitter:description"):
                self.meta_description = attr_map.get("content") or self.meta_description
        for value in attr_map.values():
            self.colors.extend(_HEX_COLOR.findall(value or ""))

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self.skip_depth:
            self.skip_depth -= 1
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.skip_depth:
            return
        text = " ".join(data.split())
        if not text:
            return
        if self.in_title:
            self.title_parts.append(text)
        self.parts.append(text)


def _string_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        value = [part.strip() for part in value.split(",")]
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def normalize_brief(data, product_name, url, extractor, note=""):
    data = data if isinstance(data, dict) else {}
    brief = {
        "brand_name": str(data.get("brand_name") or product_name or "Brand").strip(),
        "product_name": str(
            data.get("product_name") or product_name or "Product"
        ).strip(),
        "tagline": str(data.get("tagline") or "").strip(),
        "tone": str(data.get("tone") or "").strip(),
        "colors": _string_list(data.get("colors"))[:8],
        "claims": _string_list(data.get("claims"))[:8],
        "audience": str(data.get("audience") or "").strip(),
        "category": str(data.get("category") or "").strip(),
        "differentiators": _string_list(data.get("differentiators"))[:8],
        "do_not_say": _string_list(data.get("do_not_say"))[:8],
        "source_url": url or "",
        "extractor": extractor,
        "page_excerpt": str(data.get("page_excerpt") or "")[:500],
    }
    if note:
        brief["note"] = note
    return brief


def parse_html(html):
    parser = _PageParser()
    parser.feed(html or "")
    parser.close()
    title = " ".join(parser.title_parts).strip()
    text = " ".join(parser.parts)
    text = re.sub(r"\s+", " ", text).strip()
    colors = []
    for color in parser.colors:
        upper = color.upper()
        if upper not in colors:
            colors.append(upper)
    return {
        "title": title,
        "description": " ".join((parser.meta_description or "").split()),
        "text": text[:8000],
        "colors": colors[:8],
    }


def fetch_page(url, timeout=20.0, max_bytes=1_500_000):
    """Download a public http(s) page and return cleaned text fields."""
    parsed = urlparse(url or "")
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise PageFetchError("website_url must be an http(s) URL")

    headers = {"User-Agent": "NeoScaffold-AdStudio/1.0"}
    try:
        with httpx.Client(
            timeout=timeout, follow_redirects=True, headers=headers
        ) as client:
            response = client.get(url)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise PageFetchError(str(exc)) from exc

    content = response.content[:max_bytes]
    encoding = response.encoding or "utf-8"
    html = content.decode(encoding, errors="replace")
    parsed_page = parse_html(html)
    parsed_page["status_code"] = response.status_code
    return parsed_page


def heuristic_brief(page, product_name, url, note=""):
    page = page or {}
    title = page.get("title") or ""
    description = page.get("description") or ""
    brand_name = title.split("|")[0].split("–")[0].split("-")[0].strip() or product_name
    tagline = description[:180]
    return normalize_brief(
        {
            "brand_name": brand_name or product_name or "Brand",
            "product_name": product_name or brand_name or "Product",
            "tagline": tagline,
            "tone": "clear and specific",
            "colors": page.get("colors") or [],
            "claims": [description] if description else [],
            "audience": "",
            "category": "",
            "differentiators": [],
            "do_not_say": [],
            "page_excerpt": (description or title)[:500],
        },
        product_name,
        url,
        extractor="heuristic",
        note=note,
    )


def parse_json_object(text):
    raw = str(text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?", "", raw, flags=re.IGNORECASE).strip()
        raw = re.sub(r"```$", "", raw).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start : end + 1]
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("brand brief was not a JSON object")
    return data


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


class OpenAIBrandExtractor:
    """Structured extraction through the OpenAI Responses API."""

    def __init__(self, api_key=None, model=None, timeout=60):
        self.api_key = (
            api_key if api_key is not None else os.environ.get("OPENAI_API_KEY")
        )
        self.model = model or os.environ.get("AD_STUDIO_TEXT_MODEL") or "gpt-4.1-mini"
        self.timeout = timeout

    def extract(self, page_text, product_name, url):
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        try:
            from server.domain.utilities.httpx_proxies_compat import (
                apply_httpx_proxies_compat,
            )

            apply_httpx_proxies_compat()
        except Exception:
            pass
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key, timeout=self.timeout)
        prompt = _BRIEF_INSTRUCTION.format(
            product_name=product_name or "",
            url=url or "",
            page_text=(page_text or "")[:8000],
        )
        response = client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": prompt}],
                }
            ],
        )
        return parse_json_object(_response_text(response))


def default_extractor():
    if not os.environ.get("OPENAI_API_KEY"):
        return None
    return OpenAIBrandExtractor()


def build_brief(product_name, url="", page=None, extractor=None, fetch=None):
    """Fetch (unless page is provided) and extract a brief.

    Without an API key, or if the model call fails, fall back to a heuristic
    brief so the rest of the graph can still run. The ``extractor`` field
    says which path produced the brief.
    """
    note = ""
    if fetch is None:
        fetch = fetch_page
    if page is None and url:
        try:
            page = fetch(url)
        except PageFetchError as exc:
            page = {"title": "", "description": "", "text": "", "colors": []}
            note = f"Page fetch failed: {exc}"
    page = page or {"title": "", "description": "", "text": "", "colors": []}

    if extractor is None:
        try:
            extractor = default_extractor()
        except Exception as exc:
            extractor = None
            note = note or f"Brand model unavailable: {exc}"

    if extractor is None:
        return heuristic_brief(
            page,
            product_name,
            url,
            note=note or "Set OPENAI_API_KEY for LLM brand extraction.",
        )

    page_text = "\n".join(
        part
        for part in (
            page.get("title") or "",
            page.get("description") or "",
            page.get("text") or "",
        )
        if part
    )
    try:
        extracted = extractor.extract(page_text, product_name, url)
    except Exception as exc:
        brief = heuristic_brief(
            page, product_name, url, note=f"LLM extraction failed: {exc}"
        )
        return brief

    brief = normalize_brief(extracted, product_name, url, extractor="llm", note=note)
    if not brief["colors"]:
        brief["colors"] = list(page.get("colors") or [])
    return brief
