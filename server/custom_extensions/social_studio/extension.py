"""Social Studio nodes.

ACCOUNT SELECT reads the local account store.
CAPTION VARIATIONS writes N lines per creative.
DISTRIBUTE / POST assigns creatives across accounts. Dry run is the default
and does not call a platform. POST LOG reads the queue.
"""

import json

from . import captions
from .distribute import build_plan
from .scheduler import tick
from .store import get_store

version = "1.0.0"


def _input_value(node_inputs, group, name, default=None):
    return node_inputs.get(group, {}).get(name, {}).get("values", default)


def _server_from(node):
    memory = getattr(node, "_memory", None) or {}
    return memory.get("server")


def _truthy(value):
    return str(value or "").strip().lower() in ("yes", "true", "1", "y")


def _json_value(value):
    if isinstance(value, (list, dict)):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _as_creative_list(value):
    parsed = _json_value(value) if not isinstance(value, (list, dict)) else value
    if parsed is None:
        return []
    if isinstance(parsed, dict) and isinstance(parsed.get("creatives"), list):
        return [item for item in parsed["creatives"] if isinstance(item, dict)]
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    if isinstance(parsed, dict) and (
        "image_path" in parsed or "video_path" in parsed or "style_id" in parsed or "image_url" in parsed
    ):
        return [parsed]
    return []


def _collect_creatives(node_inputs):
    found = []
    found.extend(_as_creative_list(_input_value(node_inputs, "required_inputs", "creative")))
    for name in ("creative_2", "creative_3", "creative_4"):
        found.extend(_as_creative_list(_input_value(node_inputs, "optional_inputs", name)))
    return found


def _selection(node_inputs):
    parsed = _json_value(_input_value(node_inputs, "optional_inputs", "selection_json", "[]"))
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    return []


def _accounts_from(value):
    parsed = _json_value(value) if not isinstance(value, (list, dict)) else value
    if isinstance(parsed, dict) and isinstance(parsed.get("accounts"), list):
        return [item for item in parsed["accounts"] if isinstance(item, dict)]
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    return []


def _node(python_class, javascript_class_name, display_name):
    return {
        "python_class": python_class,
        "javascript_class_name": javascript_class_name,
        "display_name": display_name,
    }


class SocialAccountSelect:
    CATEGORY = "social_studio"
    SUBCATEGORY = "accounts"
    DESCRIPTION = (
        "Picks connected social accounts by tag or by id. "
        "Tokens stay in the database and are not part of this output."
    )
    INPUT = {
        "required_inputs": {},
        "optional_inputs": {
            "mode": {
                "kind": "*",
                "name": "mode",
                "widget": {"kind": "string", "name": "mode", "default": "tag"},
            },
            "tag": {
                "kind": "*",
                "name": "tag",
                "widget": {"kind": "string", "name": "tag", "default": "luma"},
            },
            "account_ids": {
                "kind": "*",
                "name": "account_ids",
                "widget": {"kind": "string", "name": "account_ids", "default": ""},
            },
        },
    }
    OUTPUT = {"kind": "*", "name": "accounts", "cacheable": False}

    def evaluate(self, node_inputs):
        mode = str(_input_value(node_inputs, "optional_inputs", "mode", "tag") or "tag").strip()
        tag = str(_input_value(node_inputs, "optional_inputs", "tag", "") or "").strip()
        raw_ids = str(_input_value(node_inputs, "optional_inputs", "account_ids", "") or "")
        store = get_store(_server_from(self))
        if mode == "ids":
            accounts = []
            for account_id in [part.strip() for part in raw_ids.split(",") if part.strip()]:
                account = store.get_account(account_id)
                if account:
                    accounts.append(account)
        else:
            accounts = store.list_accounts(tag=tag or None)
        return {
            "accounts": accounts,
            "mode": mode,
            "tag": tag,
            "count": len(accounts),
            "message": "" if accounts else "No accounts matched. Connect one at /social-studio/accounts.",
        }


class SocialCaptionVariations:
    CATEGORY = "social_studio"
    SUBCATEGORY = "compose"
    DESCRIPTION = (
        "Writes N caption and hashtag variants per creative. "
        "Uses AD_STUDIO_TEXT_MODEL when OPENAI_API_KEY is set; otherwise a heuristic."
    )
    INPUT = {
        "required_inputs": {
            "creative": {"kind": "ad_image", "name": "creative"},
        },
        "optional_inputs": {
            "creative_2": {"kind": "ad_image", "name": "creative_2"},
            "creative_3": {"kind": "ad_image", "name": "creative_3"},
            "creative_4": {"kind": "ad_image", "name": "creative_4"},
            "brand_brief": {"kind": "brand_brief", "name": "brand_brief"},
            "count": {
                "kind": "*",
                "name": "count",
                "widget": {"kind": "string", "name": "count", "default": "3"},
            },
            "tone": {
                "kind": "*",
                "name": "tone",
                "widget": {"kind": "string", "name": "tone", "default": ""},
            },
            "instructions": {
                "kind": "*",
                "name": "instructions",
                "widget": {"kind": "string", "name": "instructions", "default": ""},
            },
            "use_model": {
                "kind": "*",
                "name": "use_model",
                "widget": {"kind": "string", "name": "use_model", "default": "auto"},
            },
            "include": {
                "kind": "*",
                "name": "include",
                "widget": {"kind": "string", "name": "include", "default": "all_kept"},
            },
            "selection_json": {
                "kind": "*",
                "name": "selection_json",
                "widget": {"kind": "string", "name": "selection_json", "default": "[]"},
            },
        },
    }
    OUTPUT = {"kind": "*", "name": "caption_pack", "cacheable": False}

    def evaluate(self, node_inputs):
        from .distribute import select_creatives

        creatives = _collect_creatives(node_inputs)
        include = str(_input_value(node_inputs, "optional_inputs", "include", "all_kept") or "all_kept")
        creatives = select_creatives(creatives, include=include, selection=_selection(node_inputs))
        if not creatives:
            raise RuntimeError(
                "Caption variations need at least one kept creative. "
                "Discarded ads are skipped."
            )
        brief = _input_value(node_inputs, "optional_inputs", "brand_brief", {}) or {}
        if not isinstance(brief, dict):
            brief = {}
        generated = captions.generate_for_creatives(
            creatives,
            count=_input_value(node_inputs, "optional_inputs", "count", 3),
            tone=str(_input_value(node_inputs, "optional_inputs", "tone", "") or ""),
            instructions=str(_input_value(node_inputs, "optional_inputs", "instructions", "") or ""),
            use_model=str(_input_value(node_inputs, "optional_inputs", "use_model", "auto") or "auto"),
            brief=brief,
        )
        return {
            "creatives": creatives,
            "captions": generated["captions"],
            "model": generated["model"],
            "count": generated["count"],
        }


class SocialDistribute:
    CATEGORY = "social_studio"
    SUBCATEGORY = "publish"
    DESCRIPTION = (
        "Assigns kept creatives and captions across accounts. "
        "Dry run is on by default and writes a plan without calling publish. "
        "Live posts go to the restart-safe queue."
    )
    INPUT = {
        "required_inputs": {
            "creatives": {"kind": "caption_pack", "name": "creatives"},
            "accounts": {"kind": "account_set", "name": "accounts"},
        },
        "optional_inputs": {
            "captions": {"kind": "*", "name": "captions"},
            "strategy": {
                "kind": "*",
                "name": "strategy",
                "widget": {"kind": "string", "name": "strategy", "default": "round-robin"},
            },
            "dry_run": {
                "kind": "*",
                "name": "dry_run",
                "widget": {"kind": "string", "name": "dry_run", "default": "yes"},
            },
            "schedule_at": {
                "kind": "*",
                "name": "schedule_at",
                "widget": {"kind": "string", "name": "schedule_at", "default": ""},
            },
            "stagger_seconds": {
                "kind": "*",
                "name": "stagger_seconds",
                "widget": {"kind": "string", "name": "stagger_seconds", "default": "0"},
            },
            "jitter_seconds": {
                "kind": "*",
                "name": "jitter_seconds",
                "widget": {"kind": "string", "name": "jitter_seconds", "default": "0"},
            },
            "include": {
                "kind": "*",
                "name": "include",
                "widget": {"kind": "string", "name": "include", "default": "all_kept"},
            },
            "privacy": {
                "kind": "*",
                "name": "privacy",
                "widget": {"kind": "string", "name": "privacy", "default": "platform_default"},
            },
            "selection_json": {
                "kind": "*",
                "name": "selection_json",
                "widget": {"kind": "string", "name": "selection_json", "default": "[]"},
            },
        },
    }
    OUTPUT = {"kind": "*", "name": "post_plan", "cacheable": False}

    def evaluate(self, node_inputs):
        incoming = _input_value(node_inputs, "required_inputs", "creatives", {})
        creatives = _as_creative_list(incoming)
        captions_value = _input_value(node_inputs, "optional_inputs", "captions", None)
        if captions_value in ("", None):
            parsed = _json_value(incoming)
            captions_value = parsed.get("captions") if isinstance(parsed, dict) else None
        accounts = _accounts_from(_input_value(node_inputs, "required_inputs", "accounts", {}))
        dry_raw = _input_value(node_inputs, "optional_inputs", "dry_run", "yes")
        dry_run = True if dry_raw is None or str(dry_raw).strip() == "" else _truthy(dry_raw)
        plan = build_plan(
            creatives,
            accounts,
            captions_value,
            strategy=str(_input_value(node_inputs, "optional_inputs", "strategy", "round-robin") or "round-robin"),
            dry_run=dry_run,
            schedule_at=str(_input_value(node_inputs, "optional_inputs", "schedule_at", "") or ""),
            stagger_seconds=_input_value(node_inputs, "optional_inputs", "stagger_seconds", 0),
            jitter_seconds=_input_value(node_inputs, "optional_inputs", "jitter_seconds", 0),
            privacy=str(_input_value(node_inputs, "optional_inputs", "privacy", "platform_default") or "platform_default"),
            include=str(_input_value(node_inputs, "optional_inputs", "include", "all_kept") or "all_kept"),
            selection=_selection(node_inputs),
        )
        server = _server_from(self)
        store = get_store(server)
        store.save_plan(plan)
        for item in plan["items"]:
            store.add_post(
                {
                    "id": item["id"],
                    "account_id": item["account_id"],
                    "platform": item["platform"],
                    "handle": item["handle"],
                    "creative": item["creative"],
                    "caption": item["caption"],
                    "scheduled_at": item["scheduled_at"],
                    "status": item["status"],
                    "dry_run": item["dry_run"],
                    "error": item.get("skip_reason") or "",
                    "payload": {
                        "privacy": item.get("privacy") or "",
                        "warnings": item.get("warnings") or [],
                        "strategy": plan["strategy"],
                    },
                }
            )
        if not dry_run:
            tick(store, server=server)
            for item in plan["items"]:
                current = store.get_post(item["id"])
                if not current:
                    continue
                item["status"] = current["status"]
                item["permalink"] = current["permalink"]
                item["error"] = current["error"]
        plan["log_url"] = "/social-studio/log"
        plan["plan_url"] = "/social-studio/plan"
        return plan


class SocialPostLog:
    CATEGORY = "social_studio"
    SUBCATEGORY = "publish"
    DESCRIPTION = "Shows recent posts: account, creative, caption, schedule, permalink, or error."
    INPUT = {
        "required_inputs": {},
        "optional_inputs": {
            "plan": {"kind": "post_plan", "name": "plan"},
            "limit": {
                "kind": "*",
                "name": "limit",
                "widget": {"kind": "string", "name": "limit", "default": "20"},
            },
        },
    }
    OUTPUT = {"kind": "*", "name": "post_log", "cacheable": False}

    def evaluate(self, node_inputs):
        try:
            limit = int(_input_value(node_inputs, "optional_inputs", "limit", 20) or 20)
        except (TypeError, ValueError):
            limit = 20
        limit = max(1, min(limit, 200))
        store = get_store(_server_from(self))
        plan = _input_value(node_inputs, "optional_inputs", "plan", None)
        return {
            "posts": store.list_posts(limit),
            "plan": plan if isinstance(plan, dict) else None,
            "log_url": "/social-studio/log",
        }


EXTENSION_MAPPINGS = {
    "name": "social_studio",
    "version": version,
    "description": "Connect social accounts and distribute ad variations across them. Dry run is the default.",
    "javascript_class_name": "social_studio",
    "nodes": {
        "social_studio/SocialAccountSelect": _node(
            SocialAccountSelect, "social_studio/SocialAccountSelect", "ACCOUNT SELECT"
        ),
        "social_studio/SocialCaptionVariations": _node(
            SocialCaptionVariations,
            "social_studio/SocialCaptionVariations",
            "CAPTION VARIATIONS",
        ),
        "social_studio/SocialDistribute": _node(
            SocialDistribute, "social_studio/SocialDistribute", "DISTRIBUTE / POST"
        ),
        "social_studio/SocialPostLog": _node(
            SocialPostLog, "social_studio/SocialPostLog", "POST LOG"
        ),
    },
    "rules": {},
}


def register(server):
    """Routes, the account panel, and the restart-safe scheduler."""
    from .routes import register_routes
    from .scheduler import attach_scheduler

    register_routes(server)
    attach_scheduler(server)
