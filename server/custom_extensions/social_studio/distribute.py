"""Assign creatives and captions across accounts.

Strategies
----------
round-robin
    Creative i goes to account i % account_count. Captions walk the
    variant list so neighboring posts do not share a line when they can
    avoid it.
random
    One post per creative, shuffled onto accounts. A creative is not
    paired with the same account twice in the run.
all-to-all
    Every kept creative is posted to every selected account. Each
    account gets a different caption variant when more than one exists.

``dry_run`` builds the plan and does not call a platform.
"""

import random
from datetime import datetime, timedelta, timezone

from .constraints import check_creative, media_kind, trim_caption
from .store import new_id

STRATEGIES = ("round-robin", "random", "all-to-all")


def build_plan(
    creatives,
    accounts,
    captions=None,
    *,
    strategy="round-robin",
    dry_run=True,
    schedule_at="",
    stagger_seconds=0,
    jitter_seconds=0,
    privacy="platform_default",
    seed=None,
    include="all_kept",
    selection=None,
):
    strategy = str(strategy or "round-robin").strip().lower()
    if strategy not in STRATEGIES:
        raise ValueError(
            "strategy must be round-robin, random, or all-to-all"
        )
    creatives = select_creatives(creatives, include=include, selection=selection)
    accounts = [account for account in (accounts or []) if isinstance(account, dict)]
    if not creatives:
        raise ValueError("Distribute needs at least one kept creative.")
    if not accounts:
        raise ValueError(
            "Distribute needs at least one connected account. "
            "Open /social-studio/accounts and connect a platform, or pick a tag that has accounts."
        )
    caption_table = _caption_table(captions, len(creatives))
    rng = random.Random(seed)
    assignments = _assign(strategy, creatives, accounts, caption_table, rng)
    base = _parse_time(schedule_at)
    stagger = _nonneg(stagger_seconds)
    jitter = _nonneg(jitter_seconds)
    per_account_index = {}
    items = []
    for creative_index, account, caption in assignments:
        account_id = account.get("id") or account.get("handle") or account.get("platform")
        slot = per_account_index.get(account_id, 0)
        per_account_index[account_id] = slot + 1
        delay = slot * stagger
        if jitter and slot:
            delay += rng.randint(0, jitter)
        when = base + timedelta(seconds=delay)
        platform = str(account.get("platform") or "")
        if not str(caption or "").strip():
            creative = creatives[creative_index]
            caption = (
                creative.get("headline")
                or creative.get("style_name")
                or creative.get("product_name")
                or "New post"
            )
        trimmed, caption_warnings = trim_caption(platform, caption)
        compatible, warnings, skip_reason = check_creative(
            platform, creatives[creative_index]
        )
        warnings = list(warnings) + caption_warnings
        privacy_value, privacy_warnings = resolve_privacy(platform, privacy, account)
        warnings.extend(privacy_warnings)
        if compatible:
            status = "dry_run" if dry_run else "queued"
        else:
            status = "skipped"
        items.append(
            {
                "id": new_id(),
                "account_id": account.get("id") or "",
                "platform": platform,
                "handle": account.get("handle") or "",
                "display_name": account.get("display_name") or "",
                "creative_index": creative_index,
                "creative": summarize_creative(creatives[creative_index]),
                "caption": trimmed,
                "scheduled_at": _format_time(when),
                "compatible": compatible,
                "warnings": warnings,
                "skip_reason": skip_reason,
                "status": status,
                "privacy": privacy_value,
                "media_kind": media_kind(creatives[creative_index]),
                "dry_run": bool(dry_run),
            }
        )
    return {
        "id": new_id(),
        "dry_run": bool(dry_run),
        "strategy": strategy,
        "include": include or "all_kept",
        "privacy": privacy or "platform_default",
        "schedule_at": _format_time(base),
        "stagger_seconds": stagger,
        "jitter_seconds": jitter,
        "creative_count": len(creatives),
        "account_count": len(accounts),
        "items": items,
    }


def select_creatives(creatives, include="all_kept", selection=None):
    items = []
    for index, creative in enumerate(creatives or []):
        if not isinstance(creative, dict):
            continue
        state = _selection_for(index, creative, selection)
        discarded = bool(creative.get("discarded")) or bool(state.get("discarded"))
        favorite = bool(creative.get("favorite")) or bool(state.get("favorite"))
        if discarded:
            continue
        if str(include or "all_kept") == "favorites_only" and not favorite:
            continue
        copied = dict(creative)
        copied["favorite"] = favorite
        copied["discarded"] = False
        items.append(copied)
    return items


def summarize_creative(creative):
    creative = creative or {}
    summary = {
        "style_id": creative.get("style_id") or "",
        "style_name": creative.get("style_name") or "",
        "headline": creative.get("headline") or "",
        "image_path": creative.get("image_path") or "",
        "image_url": creative.get("image_url") or "",
        "video_path": creative.get("video_path") or "",
        "width": creative.get("width") or 0,
        "height": creative.get("height") or 0,
        "aspect": creative.get("aspect") or "",
        "placeholder": bool(creative.get("placeholder")),
        "favorite": bool(creative.get("favorite")),
        "media_kind": media_kind(creative),
    }
    prompt = str(creative.get("prompt") or "")
    if len(prompt) > 280:
        prompt = prompt[:277].rstrip() + "..."
    summary["prompt"] = prompt
    return summary


def resolve_privacy(platform, choice, account=None):
    choice = str(choice or "platform_default").strip().lower()
    if choice not in ("platform_default", "public", "private"):
        choice = "platform_default"
    extra = (account or {}).get("extra") or {}
    audited = bool(extra.get("tiktok_audited"))
    warnings = []
    if platform == "tiktok":
        if choice == "public" and audited:
            return "PUBLIC_TO_EVERYONE", warnings
        if choice == "public" and not audited:
            warnings.append(
                "TikTok unaudited apps can only post SELF_ONLY (private). "
                "Set TIKTOK_CONTENT_POSTING_AUDITED=true after the app passes audit "
                "to allow public direct posts."
            )
        elif choice in ("platform_default", "private") and not audited:
            warnings.append(
                "TikTok post is SELF_ONLY (private). Unaudited Content Posting apps cannot publish publicly."
            )
        return "SELF_ONLY", warnings
    if platform == "instagram":
        if choice == "private":
            warnings.append(
                "Instagram Content Publishing creates a feed or reel post. "
                "The API has no per-post private flag for professional accounts."
            )
        return "PUBLIC", warnings
    if platform == "facebook":
        if choice == "private":
            return "UNPUBLISHED", warnings
        return "PUBLISHED", warnings
    if platform == "x":
        if choice == "private":
            warnings.append(
                "X has no per-post private flag. The post is public unless the account itself is protected."
            )
        return "PUBLIC", warnings
    if platform == "youtube":
        if choice == "private":
            return "private", warnings
        return "public", warnings
    if platform == "linkedin":
        if choice == "private":
            return "CONNECTIONS", warnings
        return "PUBLIC", warnings
    return choice.upper(), warnings


def _assign(strategy, creatives, accounts, caption_table, rng):
    if strategy == "all-to-all":
        pairs = []
        for creative_index in range(len(creatives)):
            variants = caption_table[creative_index]
            for account_index, account in enumerate(accounts):
                caption = variants[account_index % len(variants)]
                pairs.append((creative_index, account, caption))
        return pairs
    if strategy == "random":
        order = list(range(len(creatives)))
        rng.shuffle(order)
        account_order = list(accounts)
        rng.shuffle(account_order)
        used = set()
        pairs = []
        for position, creative_index in enumerate(order):
            variants = caption_table[creative_index]
            account = _unused_account(
                creative_index, account_order, used, position
            )
            used.add((creative_index, account.get("id") or id(account)))
            caption = variants[position % len(variants)]
            pairs.append((creative_index, account, caption))
        return pairs
    pairs = []
    for creative_index, creative in enumerate(creatives):
        del creative
        account = accounts[creative_index % len(accounts)]
        variants = caption_table[creative_index]
        caption = variants[creative_index % len(variants)]
        pairs.append((creative_index, account, caption))
    return pairs


def _unused_account(creative_index, accounts, used, position):
    for offset in range(len(accounts)):
        account = accounts[(position + offset) % len(accounts)]
        key = (creative_index, account.get("id") or id(account))
        if key not in used:
            return account
    return accounts[position % len(accounts)]


def _caption_table(captions, creative_count):
    table = [[" "] for _ in range(creative_count)]
    if isinstance(captions, dict) and "captions" in captions:
        captions = captions.get("captions")
    if isinstance(captions, list) and captions and isinstance(captions[0], dict):
        for entry in captions:
            index = int(entry.get("creative_index") or 0)
            variants = [str(item).strip() for item in entry.get("variants") or [] if str(item).strip()]
            if 0 <= index < creative_count and variants:
                table[index] = variants
        return table
    if isinstance(captions, list) and captions and isinstance(captions[0], str):
        variants = [item.strip() for item in captions if str(item).strip()]
        if variants:
            for index in range(creative_count):
                table[index] = variants
        return table
    return table


def _selection_for(index, creative, selection):
    if not selection:
        return {}
    path = str(creative.get("image_path") or "")
    for item in selection:
        if not isinstance(item, dict):
            continue
        if path and item.get("image_path") and item.get("image_path") == path:
            return item
        if item.get("index") is not None and int(item.get("index")) == index:
            return item
    if index < len(selection) and isinstance(selection[index], dict):
        if selection[index].get("index") is None and not selection[index].get("image_path"):
            return selection[index]
    return {}


def _parse_time(value):
    text = str(value or "").strip()
    if not text:
        return datetime.now(timezone.utc).replace(microsecond=0)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def _format_time(value):
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _nonneg(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, number)
