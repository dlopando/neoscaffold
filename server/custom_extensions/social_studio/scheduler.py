"""Persistent post queue.

``tick`` is safe to call from a node, a test, or the background thread.
Scheduled rows live in SQLite, so a restart continues the queue.
Rate limits and retry backoff are stored on the row and in ``rate_log``.
"""

import logging
import os
import threading
from datetime import datetime, timedelta, timezone

from .media_files import media_source_from_creative
from .platforms.base import PlatformError, PlatformNotImplemented
from .platforms.registry import get_adapter
from .store import expiry_from_seconds, get_store, utc_now

logger = logging.getLogger("social_studio")

# (window seconds, max publishes in that window)
DEFAULT_RATES = {
    "tiktok": (60, 6),
    "instagram": (3600, 25),
    "facebook": (3600, 25),
    "x": (900, 15),
    "youtube": (86400, 6),
    "linkedin": (3600, 20),
}

MAX_ATTEMPTS = 4


def tick(store, adapters=None, now=None, server=None):
    """Publish due queued posts. Returns the posts after this pass."""
    now = now or utc_now()
    results = []
    for post in store.due_posts(now):
        results.append(
            execute_post(store, post, adapters=adapters, now=now, server=server)
        )
    return results


def execute_post(store, post, adapters=None, now=None, server=None):
    now = now or utc_now()
    platform = post.get("platform") or ""
    window, maximum = rate_limit(platform)
    since = shift(now, -window)
    if maximum and store.rate_count(platform, since) >= maximum:
        updated = store.update_post(
            post["id"],
            status="queued",
            next_attempt_at=shift(now, min(window, 60)),
            error=f"Rate limit: {maximum} {platform} publishes per {window}s. Will retry.",
        )
        return updated
    account = store.get_account(post.get("account_id"), include_secrets=True)
    if not account:
        return store.update_post(
            post["id"], status="failed", error="Account no longer exists."
        )
    try:
        adapter = _adapter(platform, adapters)
        account = _refresh_if_due(store, adapter, account, now)
        media = media_source_from_creative(post.get("creative") or {}, server=server)
        result = adapter.publish(
            account,
            media,
            post.get("caption") or "",
            {"privacy": (post.get("payload") or {}).get("privacy") or ""},
        )
        store.record_rate(platform, now)
        return store.update_post(
            post["id"],
            status="posted",
            permalink=result.permalink or "",
            error="",
            payload={
                "remote_id": result.remote_id,
                "warnings": list(result.warnings or []),
                "privacy": (post.get("payload") or {}).get("privacy") or "",
            },
        )
    except (PlatformNotImplemented, NotImplementedError) as exc:
        return store.update_post(
            post["id"], status="failed", error=_redact(exc, account)
        )
    except PlatformError as exc:
        attempts = int(post.get("attempts") or 0) + 1
        if exc.transient and attempts < MAX_ATTEMPTS:
            delay = min(3600, 30 * (2 ** (attempts - 1)))
            return store.update_post(
                post["id"],
                status="queued",
                attempts=attempts,
                next_attempt_at=shift(now, delay),
                error=_redact(exc, account),
            )
        return store.update_post(
            post["id"],
            status="failed",
            attempts=attempts,
            error=_redact(exc, account),
        )
    except Exception as exc:
        redacted = _redact(exc, account)
        logger.error("social studio post %s failed: %s", post.get("id"), redacted)
        return store.update_post(post["id"], status="failed", error=redacted)


def rate_limit(platform):
    raw = os.environ.get("SOCIAL_STUDIO_RATE_LIMIT_" + platform.upper(), "").strip()
    if raw and "/" in raw:
        count, seconds = raw.split("/", 1)
        try:
            return max(1, int(seconds)), max(1, int(count))
        except ValueError:
            pass
    return DEFAULT_RATES.get(platform, (60, 30))


def attach_scheduler(server):
    flag = os.environ.get("SOCIAL_STUDIO_DISABLE_SCHEDULER", "").strip().lower()
    if flag in ("1", "true", "yes"):
        return None
    if getattr(server, "_social_studio_scheduler", None):
        return server._social_studio_scheduler
    stop = threading.Event()

    def loop():
        try:
            interval = float(os.environ.get("SOCIAL_STUDIO_SCHEDULER_INTERVAL") or 15)
        except ValueError:
            interval = 15
        interval = max(2.0, interval)
        while not stop.wait(interval):
            try:
                tick(get_store(server), server=server)
            except Exception as exc:
                logger.error(
                    "social studio scheduler tick failed: %s",
                    type(exc).__name__,
                )

    thread = threading.Thread(target=loop, name="social-studio-scheduler", daemon=True)
    thread.start()
    server._social_studio_scheduler = thread
    server._social_studio_scheduler_stop = stop
    return thread


def _adapter(platform, adapters):
    if adapters and platform in adapters:
        return adapters[platform]
    return get_adapter(platform)


def _refresh_if_due(store, adapter, account, now):
    expiry = account.get("token_expiry") or ""
    if not expiry or expiry > shift(now, 120):
        return account
    if not account.get("refresh_token") and not account.get("access_token"):
        return account
    bundle = adapter.refresh(account)
    updated = store.update_tokens(
        account["id"],
        access_token=bundle.access_token,
        refresh_token=bundle.refresh_token or account.get("refresh_token") or "",
        token_expiry=expiry_from_seconds(bundle.expires_in) if bundle.expires_in else account.get("token_expiry"),
        status="connected",
    )
    return store.get_account(updated["id"], include_secrets=True)


def _redact(exc, account):
    text = str(exc)[:500]
    for key in ("access_token", "refresh_token"):
        secret = str((account or {}).get(key) or "")
        if len(secret) >= 6 and secret in text:
            text = text.replace(secret, "[redacted]")
    return text


def shift(now, seconds):
    parsed = datetime.strptime(now, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return (parsed + timedelta(seconds=int(seconds))).strftime("%Y-%m-%dT%H:%M:%SZ")
