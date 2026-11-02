"""HTML for the account manager, the dry-run plan, and the post log."""

import html

_CSS = """
:root {
  color-scheme: dark;
  --bg: #101218;
  --card: #1b1e27;
  --line: rgba(255,255,255,0.12);
  --text: #f4f6fb;
  --muted: #a7adbb;
  --accent: #8eb4ff;
  --good: #3ddc97;
  --warn: #ffb020;
  --bad: #ff6b7a;
  --chip: #2a3142;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--text);
  font: 15px/1.45 ui-sans-serif, system-ui, -apple-system, sans-serif;
}
a { color: var(--accent); }
header, main { width: min(1100px, calc(100% - 32px)); margin: 0 auto; }
header { padding: 28px 0 8px; }
h1 { font-size: 28px; margin: 0 0 6px; letter-spacing: -0.03em; }
.sub { color: var(--muted); margin: 0 0 16px; }
nav { display: flex; gap: 14px; margin-bottom: 18px; }
.banner {
  border: 1px solid var(--line); background: #2a2214; color: #ffe3ad;
  border-radius: 12px; padding: 10px 14px; margin: 8px 0 16px;
}
.banner strong { color: #fff; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }
.card {
  background: var(--card); border: 1px solid var(--line); border-radius: 16px; padding: 14px;
}
.card h2 { margin: 0 0 4px; font-size: 18px; }
.handle { color: var(--muted); margin: 0 0 8px; }
.row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.chip, .tag {
  display: inline-flex; align-items: center; border-radius: 999px;
  padding: 2px 8px; background: var(--chip); color: var(--text); font-size: 12px;
}
.tag { background: #243044; color: #d5e4ff; }
.status-connected { color: var(--good); }
.status-expired, .status-failed { color: var(--bad); }
.status-placeholder, .status-dry_run, .status-queued { color: var(--warn); }
.status-posted, .status-skipped { color: var(--muted); }
button, .button {
  background: #2c364c; color: var(--text); border: 1px solid var(--line);
  border-radius: 10px; padding: 8px 12px; text-decoration: none; cursor: pointer;
  font: inherit;
}
button.primary, a.primary { background: #35548f; }
button.danger { background: #6d2d36; }
form.inline { display: inline; }
label { display: block; font-size: 12px; color: var(--muted); margin-top: 8px; }
input, select {
  width: 100%; margin-top: 4px; background: #12151c; color: var(--text);
  border: 1px solid var(--line); border-radius: 8px; padding: 8px;
}
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--line); vertical-align: top; }
th { color: var(--muted); font-weight: 600; font-size: 12px; }
.note { color: var(--muted); font-size: 13px; }
.ribbon {
  display: inline-block; background: #6d2430; color: #ffe8e8; font-weight: 700;
  letter-spacing: 0.08em; font-size: 12px; border-radius: 8px; padding: 4px 8px;
}
footer { color: var(--muted); padding: 28px 0 40px; font-size: 13px; }
"""


def accounts_page(accounts, catalog, *, placeholder=False, notice=""):
    parts = [
        "<p class=\"sub\">One place for every connected account. Tokens stay encrypted on the server and are not shown here.</p>",
        "<nav><a href=\"/social-studio/accounts\">Accounts</a><a href=\"/social-studio/plan\">Dry-run plan</a>"
        "<a href=\"/social-studio/log\">Post log</a><a href=\"/social-studio/preview\">Example workflow</a></nav>",
    ]
    if notice:
        parts.append(f"<div class=\"banner\">{esc(notice)}</div>")
    if placeholder:
        parts.append(
            "<div class=\"banner\"><span class=\"ribbon\">PLACEHOLDER</span> "
            "Sample accounts for the panel. Nothing is connected and nothing will be posted.</div>"
        )
    parts.append("<section class=\"card\"><h2>Connect</h2><div class=\"row\">")
    for item in catalog:
        label = "Reconnect " + item["label"] if item.get("configured") else "Connect " + item["label"]
        parts.append(
            f"<a class=\"button primary\" href=\"/social-studio/connect/{esc(item['platform'])}\">{esc(label)}</a>"
        )
    parts.append("</div><p class=\"note\">Each button starts that platform's own OAuth screen. "
                 "Missing client env vars return a setup error instead of a fake account.</p>")
    missing = []
    for item in catalog:
        if item.get("missing"):
            missing.append(item["label"] + ": " + ", ".join(item["missing"]))
    if missing:
        parts.append("<p class=\"note\">Not configured — " + esc("; ".join(missing)) + "</p>")
    parts.append("</section>")
    parts.append("<h2 style=\"margin-top:22px\">Accounts</h2><div class=\"grid\">")
    if not accounts:
        parts.append("<p class=\"note\">No accounts yet.</p>")
    for account in accounts:
        parts.append(_account_card(account, placeholder=placeholder))
    parts.append("</div>")
    parts.append(_manual_form(catalog))
    parts.append(
        "<footer>Groups are tags. TikTok apps that have not passed audit can only post SELF_ONLY (private). "
        "Open the README in custom_extensions/social_studio for every env var.</footer>"
    )
    return _document("Social accounts", "".join(parts))


def plan_page(plan, *, placeholder=False):
    parts = [
        "<p class=\"sub\">The latest distribute plan. Dry run does everything except the platform publish call.</p>",
        "<nav><a href=\"/social-studio/accounts\">Accounts</a><a href=\"/social-studio/plan\">Dry-run plan</a>"
        "<a href=\"/social-studio/log\">Post log</a></nav>",
    ]
    if placeholder or not plan:
        parts.append(
            "<div class=\"banner\"><span class=\"ribbon\">PLACEHOLDER</span> "
            "<span class=\"ribbon\">DRY RUN</span> "
            "This preview is sample data. Run DISTRIBUTE / POST to replace it with a real plan.</div>"
        )
        plan = _placeholder_plan()
    elif plan.get("dry_run"):
        parts.append(
            "<div class=\"banner\"><span class=\"ribbon\">DRY RUN</span> "
            "Publish was not called. Turn dry run off on the node to queue live posts.</div>"
        )
    parts.append(
        "<p class=\"note\">Strategy "
        + esc(plan.get("strategy") or "")
        + " · "
        + esc(str(plan.get("creative_count", "")))
        + " creatives · "
        + esc(str(plan.get("account_count", "")))
        + " accounts</p>"
    )
    parts.append(_plan_table(plan.get("items") or []))
    parts.append("<footer>Permalinks appear after a live post succeeds. Errors stay on the row.</footer>")
    return _document("Dry-run plan", "".join(parts))


def log_page(posts, *, placeholder=False):
    parts = [
        "<p class=\"sub\">Each row is one planned or finished post.</p>",
        "<nav><a href=\"/social-studio/accounts\">Accounts</a><a href=\"/social-studio/plan\">Dry-run plan</a>"
        "<a href=\"/social-studio/log\">Post log</a></nav>",
    ]
    if placeholder or not posts:
        parts.append(
            "<div class=\"banner\"><span class=\"ribbon\">PLACEHOLDER</span> "
            "Sample log rows. The queue is empty.</div>"
        )
        posts = _placeholder_posts()
    parts.append(_post_table(posts))
    return _document("Post log", "".join(parts))


def message_page(title, message, status_hint=""):
    body = (
        "<nav><a href=\"/social-studio/accounts\">Back to accounts</a></nav>"
        f"<div class=\"banner\">{esc(message)}</div>"
        f"<p class=\"note\">{esc(status_hint)}</p>"
    )
    return _document(title, body)


def _document(title, body):
    return (
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\"/>"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/>"
        f"<title>{esc(title)}</title><style>{_CSS}</style></head><body>"
        f"<header><h1>{esc(title)}</h1></header><main>{body}</main></body></html>"
    )


def _account_card(account, placeholder=False):
    status = account.get("status") or ""
    tags = account.get("tags") or []
    note = (account.get("extra") or {}).get("privacy_note") or ""
    tag_html = "".join(f"<span class=\"tag\">{esc(tag)}</span>" for tag in tags)
    actions = ""
    if not placeholder and account.get("id"):
        actions = (
            "<form method=\"post\" action=\"/social-studio/accounts/"
            + esc(account["id"])
            + "/tag\">"
            "<label>Add to group<input name=\"tag\" placeholder=\"launch\"/></label>"
            "<button type=\"submit\">Add tag</button></form>"
            "<form method=\"post\" action=\"/social-studio/accounts/"
            + esc(account["id"])
            + "/delete\" class=\"inline\">"
            "<button class=\"danger\" type=\"submit\">Remove</button></form>"
        )
    return (
        "<article class=\"card\">"
        f"<div class=\"row\"><span class=\"chip\">{esc(account.get('platform'))}</span>"
        f"<span class=\"status-{esc(status)}\">{esc(status)}</span></div>"
        f"<h2>{esc(account.get('display_name') or '')}</h2>"
        f"<p class=\"handle\">{esc(account.get('handle') or '')}</p>"
        f"<div class=\"row\">{tag_html}</div>"
        f"<p class=\"note\">Token expiry {esc(account.get('token_expiry') or 'unknown')}</p>"
        + (f"<p class=\"note\">{esc(note)}</p>" if note else "")
        + actions
        + "</article>"
    )


def _manual_form(catalog):
    options = "".join(
        f"<option value=\"{esc(item['platform'])}\">{esc(item['label'])}</option>"
        for item in catalog
    )
    return (
        "<details class=\"card\" style=\"margin-top:18px\"><summary>Add an account with a token you already have</summary>"
        "<form method=\"post\" action=\"/social-studio/accounts\">"
        f"<label>Platform<select name=\"platform\">{options}</select></label>"
        "<label>Handle<input name=\"handle\" placeholder=\"@luma\"/></label>"
        "<label>Display name<input name=\"display_name\" placeholder=\"Luma\"/></label>"
        "<label>Tags<input name=\"tags\" placeholder=\"skincare, launch\"/></label>"
        "<label>Access token<input name=\"access_token\" type=\"password\" autocomplete=\"off\"/></label>"
        "<label>Refresh token<input name=\"refresh_token\" type=\"password\" autocomplete=\"off\"/></label>"
        "<label>Expires in seconds<input name=\"expires_in\" placeholder=\"3600\"/></label>"
        "<p class=\"note\">The token is encrypted with SOCIAL_STUDIO_SECRET_KEY and the response never echoes it.</p>"
        "<button class=\"primary\" type=\"submit\">Save account</button></form></details>"
    )


def _plan_table(items):
    rows = []
    for item in items:
        creative = item.get("creative") or {}
        name = creative.get("style_name") or creative.get("headline") or "creative"
        warnings = "; ".join(item.get("warnings") or [])
        if item.get("skip_reason"):
            warnings = (warnings + "; " if warnings else "") + item["skip_reason"]
        rows.append(
            "<tr>"
            f"<td>{esc(item.get('platform'))}<br/><span class=\"note\">{esc(item.get('handle'))}</span></td>"
            f"<td>{esc(name)}<br/><span class=\"note\">{esc(creative.get('aspect') or '')} {esc(creative.get('media_kind') or '')}</span></td>"
            f"<td>{esc(item.get('caption'))}</td>"
            f"<td>{esc(item.get('scheduled_at'))}</td>"
            f"<td class=\"status-{esc(item.get('status'))}\">{esc(item.get('status'))}</td>"
            f"<td class=\"note\">{esc(warnings)}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>Account</th><th>Creative</th><th>Caption</th>"
        "<th>Scheduled</th><th>Result</th><th>Notes</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _post_table(posts):
    rows = []
    for post in posts:
        creative = post.get("creative") or {}
        link = post.get("permalink") or ""
        result = link or post.get("error") or post.get("status") or ""
        rows.append(
            "<tr>"
            f"<td>{esc(post.get('platform'))}<br/><span class=\"note\">{esc(post.get('handle'))}</span></td>"
            f"<td>{esc(creative.get('style_name') or creative.get('headline') or '')}</td>"
            f"<td>{esc(post.get('caption'))}</td>"
            f"<td>{esc(post.get('scheduled_at'))}</td>"
            f"<td>{esc(result)}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>Account</th><th>Creative</th><th>Caption</th>"
        "<th>Scheduled</th><th>Result</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def placeholder_accounts():
    return [
        {
            "platform": "tiktok",
            "handle": "@luma.labs",
            "display_name": "Luma Labs",
            "tags": ["skincare", "launch"],
            "status": "placeholder",
            "token_expiry": "2026-12-01T00:00:00Z",
            "extra": {
                "privacy_note": "PLACEHOLDER. Unaudited TikTok apps post SELF_ONLY (private) until the app is audited."
            },
        },
        {
            "platform": "instagram",
            "handle": "@luma.serum",
            "display_name": "Luma Serum",
            "tags": ["skincare"],
            "status": "placeholder",
            "token_expiry": "2026-12-15T00:00:00Z",
            "extra": {"privacy_note": "PLACEHOLDER. Professional Instagram account linked to a Facebook Page."},
        },
        {
            "platform": "x",
            "handle": "@luma",
            "display_name": "Luma",
            "tags": ["launch"],
            "status": "placeholder",
            "token_expiry": "2026-11-20T00:00:00Z",
            "extra": {"privacy_note": "PLACEHOLDER. X OAuth 2.0 PKCE. Tier write caps still apply."},
        },
        {
            "platform": "linkedin",
            "handle": "Luma Skin",
            "display_name": "Luma Skin",
            "tags": ["skincare", "b2b"],
            "status": "placeholder",
            "token_expiry": "2026-11-30T00:00:00Z",
            "extra": {"privacy_note": "PLACEHOLDER. Member post. Organization posts need product approval."},
        },
    ]


def _placeholder_plan():
    return {
        "strategy": "round-robin",
        "dry_run": True,
        "creative_count": 3,
        "account_count": 4,
        "items": [
            {
                "platform": "tiktok",
                "handle": "@luma.labs",
                "creative": {"style_name": "Claymation", "aspect": "9:16", "media_kind": "image"},
                "caption": "PLACEHOLDER. Stop scrolling. Luma Serum — clay, witty. #LumaSerum #ad",
                "scheduled_at": "2026-11-02T18:00:00Z",
                "status": "dry_run",
                "warnings": [
                    "PLACEHOLDER data. TikTok unaudited apps can only post SELF_ONLY (private)."
                ],
            },
            {
                "platform": "instagram",
                "handle": "@luma.serum",
                "creative": {"style_name": "Don't Buy This", "aspect": "1:1", "media_kind": "image"},
                "caption": "PLACEHOLDER. We almost didn't post this. #LumaSerum #launch",
                "scheduled_at": "2026-11-02T18:00:00Z",
                "status": "dry_run",
                "warnings": ["PLACEHOLDER. Instagram needs a public HTTPS image URL on a live post."],
            },
            {
                "platform": "x",
                "handle": "@luma",
                "creative": {"style_name": "Claymation 9:16", "aspect": "9:16", "media_kind": "image"},
                "caption": "PLACEHOLDER. The bottle is the whole ad.",
                "scheduled_at": "2026-11-02T18:01:30Z",
                "status": "dry_run",
                "warnings": ["PLACEHOLDER. Caption fits the 280 character X limit."],
            },
            {
                "platform": "youtube",
                "handle": "@LumaSkin",
                "creative": {"style_name": "Still frame", "aspect": "1:1", "media_kind": "image"},
                "caption": "PLACEHOLDER. This still would be skipped.",
                "scheduled_at": "2026-11-02T18:01:30Z",
                "status": "skipped",
                "skip_reason": "youtube does not publish still images through this adapter",
                "warnings": ["PLACEHOLDER. YouTube Shorts need a video file."],
            },
        ],
    }


def _placeholder_posts():
    plan = _placeholder_plan()
    posts = []
    for item in plan["items"]:
        posts.append(
            {
                "platform": item["platform"],
                "handle": item["handle"],
                "creative": item["creative"],
                "caption": item["caption"],
                "scheduled_at": item["scheduled_at"],
                "status": item["status"],
                "permalink": "",
                "error": item.get("skip_reason") or "DRY RUN — publish was not called. PLACEHOLDER.",
            }
        )
    return posts


def esc(value):
    return html.escape(str(value if value is not None else ""), quote=True)
