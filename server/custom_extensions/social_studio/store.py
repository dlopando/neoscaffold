"""SQLite store for social accounts, the post queue, and OAuth state.

Access tokens and refresh tokens are encrypted before they touch the
database. Public serializers omit them.
"""

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone

from . import paths
from .crypto import decrypt, encrypt

_SECRET_KEYS = {
    "access_token",
    "refresh_token",
    "access_token_enc",
    "refresh_token_enc",
    "page_access_token",
    "client_secret",
}


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id():
    return uuid.uuid4().hex


class SocialStore:
    def __init__(self, db_path):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._migrate()

    def close(self):
        with self._lock:
            self._conn.close()

    def _migrate(self):
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    id TEXT PRIMARY KEY,
                    platform TEXT NOT NULL,
                    handle TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    external_id TEXT NOT NULL DEFAULT '',
                    tags TEXT NOT NULL,
                    status TEXT NOT NULL,
                    token_expiry TEXT,
                    access_token_enc TEXT,
                    refresh_token_enc TEXT,
                    scopes TEXT NOT NULL,
                    extra_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS posts (
                    id TEXT PRIMARY KEY,
                    account_id TEXT,
                    platform TEXT,
                    handle TEXT,
                    creative_json TEXT,
                    caption TEXT,
                    scheduled_at TEXT,
                    status TEXT,
                    permalink TEXT,
                    error TEXT,
                    dry_run INTEGER NOT NULL DEFAULT 0,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at TEXT,
                    payload_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS posts_due
                    ON posts (status, scheduled_at);
                CREATE TABLE IF NOT EXISTS oauth_states (
                    state TEXT PRIMARY KEY,
                    platform TEXT NOT NULL,
                    code_verifier TEXT,
                    redirect_uri TEXT,
                    extra_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS rate_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    ts TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS plans (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    plan_json TEXT NOT NULL
                );
                """
            )
            self._conn.commit()

    def _write(self, sql, params=()):
        with self._lock:
            cursor = self._conn.execute(sql, params)
            self._conn.commit()
            return cursor

    def _read(self, sql, params=()):
        with self._lock:
            return list(self._conn.execute(sql, params))

    def upsert_account(
        self,
        *,
        platform,
        handle,
        display_name,
        external_id="",
        tags=None,
        status="connected",
        token_expiry=None,
        access_token="",
        refresh_token="",
        scopes=None,
        extra=None,
        account_id=None,
    ):
        now = utc_now()
        tags = list(tags or [])
        scopes = list(scopes or [])
        extra = _scrub(extra or {})
        access_enc = encrypt(access_token) if access_token else ""
        refresh_enc = encrypt(refresh_token) if refresh_token else ""
        existing = None
        if external_id:
            rows = self._read(
                "SELECT id FROM accounts WHERE platform = ? AND external_id = ?",
                (platform, external_id),
            )
            if rows:
                existing = rows[0]["id"]
        if account_id and not existing:
            rows = self._read("SELECT id FROM accounts WHERE id = ?", (account_id,))
            if rows:
                existing = account_id
        if existing:
            self._write(
                """
                UPDATE accounts SET
                    handle = ?, display_name = ?, external_id = ?, tags = ?,
                    status = ?, token_expiry = ?, access_token_enc = ?,
                    refresh_token_enc = ?, scopes = ?, extra_json = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    handle,
                    display_name,
                    external_id or "",
                    json.dumps(tags),
                    status,
                    token_expiry,
                    access_enc,
                    refresh_enc,
                    json.dumps(scopes),
                    json.dumps(extra),
                    now,
                    existing,
                ),
            )
            return self.get_account(existing)
        account_id = account_id or new_id()
        self._write(
            """
            INSERT INTO accounts (
                id, platform, handle, display_name, external_id, tags, status,
                token_expiry, access_token_enc, refresh_token_enc, scopes,
                extra_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                account_id,
                platform,
                handle,
                display_name,
                external_id or "",
                json.dumps(tags),
                status,
                token_expiry,
                access_enc,
                refresh_enc,
                json.dumps(scopes),
                json.dumps(extra),
                now,
                now,
            ),
        )
        return self.get_account(account_id)

    def list_accounts(self, tag=None, platform=None):
        rows = self._read("SELECT * FROM accounts ORDER BY platform, handle")
        accounts = [self._public_account(row) for row in rows]
        if platform:
            accounts = [item for item in accounts if item["platform"] == platform]
        if tag:
            accounts = [item for item in accounts if tag in item["tags"]]
        return accounts

    def get_account(self, account_id, include_secrets=False):
        rows = self._read("SELECT * FROM accounts WHERE id = ?", (account_id,))
        if not rows:
            return None
        if include_secrets:
            return self._secret_account(rows[0])
        return self._public_account(rows[0])

    def remove_account(self, account_id):
        self._write("DELETE FROM accounts WHERE id = ?", (account_id,))

    def set_tags(self, account_id, tags):
        cleaned = []
        for tag in tags or []:
            text = str(tag or "").strip()
            if text and text not in cleaned:
                cleaned.append(text)
        now = utc_now()
        self._write(
            "UPDATE accounts SET tags = ?, updated_at = ? WHERE id = ?",
            (json.dumps(cleaned), now, account_id),
        )
        return self.get_account(account_id)

    def add_tag(self, account_id, tag):
        account = self.get_account(account_id)
        if not account:
            return None
        tags = list(account["tags"])
        text = str(tag or "").strip()
        if text and text not in tags:
            tags.append(text)
        return self.set_tags(account_id, tags)

    def remove_tag(self, account_id, tag):
        account = self.get_account(account_id)
        if not account:
            return None
        text = str(tag or "").strip()
        return self.set_tags(
            account_id, [item for item in account["tags"] if item != text]
        )

    def update_tokens(
        self, account_id, *, access_token, refresh_token="", token_expiry=None, status="connected"
    ):
        now = utc_now()
        self._write(
            """
            UPDATE accounts SET
                access_token_enc = ?, refresh_token_enc = ?, token_expiry = ?,
                status = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                encrypt(access_token) if access_token else "",
                encrypt(refresh_token) if refresh_token else "",
                token_expiry,
                status,
                now,
                account_id,
            ),
        )
        return self.get_account(account_id)

    def add_post(self, post):
        now = utc_now()
        post_id = post.get("id") or new_id()
        payload = _scrub(post.get("payload") or {})
        creative = _scrub(post.get("creative") or {})
        self._write(
            """
            INSERT INTO posts (
                id, account_id, platform, handle, creative_json, caption,
                scheduled_at, status, permalink, error, dry_run, attempts,
                next_attempt_at, payload_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                post_id,
                post.get("account_id") or "",
                post.get("platform") or "",
                post.get("handle") or "",
                json.dumps(creative),
                post.get("caption") or "",
                post.get("scheduled_at") or now,
                post.get("status") or "queued",
                post.get("permalink") or "",
                post.get("error") or "",
                1 if post.get("dry_run") else 0,
                int(post.get("attempts") or 0),
                post.get("next_attempt_at"),
                json.dumps(payload),
                now,
                now,
            ),
        )
        return self.get_post(post_id)

    def get_post(self, post_id):
        rows = self._read("SELECT * FROM posts WHERE id = ?", (post_id,))
        if not rows:
            return None
        return _public_post(rows[0])

    def list_posts(self, limit=100):
        rows = self._read(
            "SELECT * FROM posts ORDER BY created_at DESC, id DESC LIMIT ?",
            (int(limit),),
        )
        return [_public_post(row) for row in rows]

    def due_posts(self, now=None, limit=20):
        now = now or utc_now()
        rows = self._read(
            """
            SELECT * FROM posts
            WHERE status = 'queued'
              AND scheduled_at <= ?
              AND (next_attempt_at IS NULL OR next_attempt_at = '' OR next_attempt_at <= ?)
            ORDER BY scheduled_at ASC, id ASC
            LIMIT ?
            """,
            (now, now, int(limit)),
        )
        return [_public_post(row) for row in rows]

    def update_post(self, post_id, **fields):
        allowed = {
            "status",
            "permalink",
            "error",
            "attempts",
            "next_attempt_at",
            "scheduled_at",
            "payload",
        }
        assignments = []
        params = []
        for key, value in fields.items():
            if key not in allowed:
                continue
            column = "payload_json" if key == "payload" else key
            if key == "payload":
                value = json.dumps(_scrub(value or {}))
            assignments.append(f"{column} = ?")
            params.append(value)
        if not assignments:
            return self.get_post(post_id)
        assignments.append("updated_at = ?")
        params.append(utc_now())
        params.append(post_id)
        self._write(
            f"UPDATE posts SET {', '.join(assignments)} WHERE id = ?",
            params,
        )
        return self.get_post(post_id)

    def save_oauth_state(self, *, state, platform, code_verifier="", redirect_uri="", extra=None):
        self._write(
            """
            INSERT OR REPLACE INTO oauth_states
                (state, platform, code_verifier, redirect_uri, extra_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                state,
                platform,
                code_verifier or "",
                redirect_uri or "",
                json.dumps(_scrub(extra or {})),
                utc_now(),
            ),
        )

    def pop_oauth_state(self, state):
        rows = self._read("SELECT * FROM oauth_states WHERE state = ?", (state,))
        if not rows:
            return None
        self._write("DELETE FROM oauth_states WHERE state = ?", (state,))
        row = rows[0]
        return {
            "state": row["state"],
            "platform": row["platform"],
            "code_verifier": row["code_verifier"] or "",
            "redirect_uri": row["redirect_uri"] or "",
            "extra": json.loads(row["extra_json"] or "{}"),
            "created_at": row["created_at"],
        }

    def record_rate(self, platform, ts=None):
        self._write(
            "INSERT INTO rate_log (platform, ts) VALUES (?, ?)",
            (platform, ts or utc_now()),
        )

    def rate_count(self, platform, since):
        rows = self._read(
            "SELECT COUNT(*) AS n FROM rate_log WHERE platform = ? AND ts >= ?",
            (platform, since),
        )
        return int(rows[0]["n"]) if rows else 0

    def save_plan(self, plan):
        plan_id = plan.get("id") or new_id()
        stored = dict(plan)
        stored["id"] = plan_id
        self._write(
            "INSERT INTO plans (id, created_at, plan_json) VALUES (?, ?, ?)",
            (plan_id, utc_now(), json.dumps(_scrub(stored))),
        )
        return stored

    def latest_plan(self):
        rows = self._read(
            "SELECT plan_json FROM plans ORDER BY created_at DESC LIMIT 1"
        )
        if not rows:
            return None
        return json.loads(rows[0]["plan_json"])

    def _public_account(self, row):
        expiry = row["token_expiry"] or ""
        status = row["status"]
        if expiry and status == "connected" and expiry < utc_now():
            status = "expired"
        return {
            "id": row["id"],
            "platform": row["platform"],
            "handle": row["handle"],
            "display_name": row["display_name"],
            "external_id": row["external_id"] or "",
            "tags": json.loads(row["tags"] or "[]"),
            "status": status,
            "token_expiry": expiry,
            "scopes": json.loads(row["scopes"] or "[]"),
            "extra": json.loads(row["extra_json"] or "{}"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _secret_account(self, row):
        public = self._public_account(row)
        public["access_token"] = (
            decrypt(row["access_token_enc"]) if row["access_token_enc"] else ""
        )
        public["refresh_token"] = (
            decrypt(row["refresh_token_enc"]) if row["refresh_token_enc"] else ""
        )
        return public


def _public_post(row):
    return {
        "id": row["id"],
        "account_id": row["account_id"] or "",
        "platform": row["platform"] or "",
        "handle": row["handle"] or "",
        "creative": json.loads(row["creative_json"] or "{}"),
        "caption": row["caption"] or "",
        "scheduled_at": row["scheduled_at"] or "",
        "status": row["status"] or "",
        "permalink": row["permalink"] or "",
        "error": row["error"] or "",
        "dry_run": bool(row["dry_run"]),
        "attempts": int(row["attempts"] or 0),
        "next_attempt_at": row["next_attempt_at"] or "",
        "payload": json.loads(row["payload_json"] or "{}"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _scrub(value):
    """Drop anything that looks like a credential before it is stored in JSON."""
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if str(key) in _SECRET_KEYS:
                continue
            cleaned[key] = _scrub(item)
        return cleaned
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    return value


_STORES = {}
_STORE_LOCK = threading.Lock()


def get_store(server=None):
    path = paths.database_path(server)
    with _STORE_LOCK:
        store = _STORES.get(path)
        if store is None:
            store = SocialStore(path)
            _STORES[path] = store
        return store


def expiry_from_seconds(seconds, now=None):
    if not seconds:
        return ""
    base = datetime.now(timezone.utc) if now is None else now
    if isinstance(base, str):
        base = datetime.strptime(base, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    from datetime import timedelta

    return (base + timedelta(seconds=int(seconds))).strftime("%Y-%m-%dT%H:%M:%SZ")
