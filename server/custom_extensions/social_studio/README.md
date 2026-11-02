# Social Studio

Multi-account posting for NeoScaffold. One operator connects many accounts,
keeps the Ad Studio creatives they like, and distributes caption variations
across those accounts. The platform calls go to each network's official API.
There is no aggregator.

Dry run is the default. It builds the plan, writes the log, and does not
call publish.

## Run it

From `server/`:

```bash
export SOCIAL_STUDIO_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export SOCIAL_STUDIO_PUBLIC_BASE="http://127.0.0.1:6166"
python main.py
```

Open:

- Accounts: http://127.0.0.1:6166/social-studio/accounts
- Dry-run plan: http://127.0.0.1:6166/social-studio/plan
- Post log: http://127.0.0.1:6166/social-studio/log
- Example graph: http://127.0.0.1:6166/social-studio/preview

The Ember app at port 4200 loads `web.js` with the other extensions. A
"Social accounts" button sits on the workflow canvas. The example graph is
`example_workflows/social_studio_dry_run.json`.

Regenerate that graph with:

```bash
python -m custom_extensions.social_studio.build_workflow
```

Add `?demo=1` to the accounts, plan, or log URL to force the labeled
placeholder data.

## What the nodes do

1. **ACCOUNT SELECT** reads accounts by tag (a group) or by id. The wire
   carries public fields only.
2. **CAPTION VARIATIONS** takes up to four creatives (or a list) plus an
   optional brand brief. Discarded creatives are skipped. Favorites-only is
   a widget. With `OPENAI_API_KEY`, `use_model=auto` calls
   `AD_STUDIO_TEXT_MODEL` (default `gpt-4.1-mini`). Without a key, or when
   `use_model=no`, a heuristic writes the lines.
3. **DISTRIBUTE / POST** assigns creatives with `round-robin`, `random`
   (no repeated creative/account pair), or `all-to-all`. It checks aspect
   and file size, trims captions, applies a schedule plus per-account
   stagger and jitter, and writes a plan. `dry_run=yes` is the default.
   `dry_run=no` enqueues rows for the scheduler, which publishes anything
   already due.
4. **POST LOG** lists those rows. The same data is on `/social-studio/log`.

The queue is SQLite at `{output}/social_studio/social_studio.db`. It
survives a restart. The background thread starts with the extension unless
`SOCIAL_STUDIO_DISABLE_SCHEDULER=1`.

## Tokens

`SOCIAL_STUDIO_SECRET_KEY` is required before a token can be stored. Tokens
are encrypted (SHA-256 counter mode plus HMAC-SHA256) and the plaintext is
not returned by the API, not written into post payloads, and not written
into log lines. Losing the key makes stored tokens unreadable. Rotate it
only after reconnecting every account.

Manual token entry exists for a token you already hold. The field is
write-only.

## Environment variables

Shared:

| Variable | Required | Purpose |
| --- | --- | --- |
| `SOCIAL_STUDIO_SECRET_KEY` | yes, to store tokens | Encryption key. Use a long random string. |
| `SOCIAL_STUDIO_PUBLIC_BASE` | yes, for OAuth if a platform redirect var is unset | Origin of this server, no trailing path. Redirect becomes `{base}/social-studio/oauth/{platform}/callback`. |
| `SOCIAL_STUDIO_PUBLIC_MEDIA_BASE` | for TikTok photos and Instagram | Public HTTPS origin that reaches this server. Files are copied under `/social-studio/media/{name}`. |
| `SOCIAL_STUDIO_DATABASE` | no | Override the SQLite path. |
| `SOCIAL_STUDIO_DISABLE_SCHEDULER` | no | `1` keeps the queue but does not start the thread. |
| `SOCIAL_STUDIO_SCHEDULER_INTERVAL` | no | Seconds between queue scans. Default 15. |
| `SOCIAL_STUDIO_RATE_LIMIT_{PLATFORM}` | no | `count/seconds`, for example `SOCIAL_STUDIO_RATE_LIMIT_X=15/900`. |
| `OPENAI_API_KEY` | no | Enables model captions. |
| `AD_STUDIO_TEXT_MODEL` | no | Caption model. Default `gpt-4.1-mini`. This extension does not change the Ad Studio image model. |
| `NEOSCAFFOLD_OUTPUT_DIRECTORY` | no | Output root when the server flag is not set. |

Defaults for the rate limiter: TikTok 6/minute, Instagram 25/hour,
Facebook 25/hour, X 15 per 15 minutes, YouTube 6/day, LinkedIn 20/hour.
A limited platform is postponed. It is not marked failed. Transient HTTP
429/5xx retries up to 4 times with backoff 30s, 60s, 120s, then stops.

### TikTok

| Variable | Required |
| --- | --- |
| `TIKTOK_CLIENT_KEY` | yes |
| `TIKTOK_CLIENT_SECRET` | yes |
| `TIKTOK_REDIRECT_URI` | no, if `SOCIAL_STUDIO_PUBLIC_BASE` is set |
| `TIKTOK_CONTENT_POSTING_AUDITED` | no. Default false. `true` only after TikTok approves the app |

Create the app at https://developers.tiktok.com/. Add the Content Posting
API product. Scopes requested: `user.info.basic`, `user.info.profile`,
`video.publish`, `video.upload`.

Redirect URI: `{SOCIAL_STUDIO_PUBLIC_BASE}/social-studio/oauth/tiktok/callback`.

Unaudited apps may only send `privacy_level=SELF_ONLY`. The accounts panel,
the plan, and the publish call say that plainly. Public direct post
(`PUBLIC_TO_EVERYONE`) is used only when `TIKTOK_CONTENT_POSTING_AUDITED=true`.
Direct Post for photos is `PULL_FROM_URL` (a public HTTPS image). Video
direct post uploads the file. Docs:
https://developers.tiktok.com/doc/content-posting-api-get-started

### Instagram (professional accounts)

| Variable | Required |
| --- | --- |
| `INSTAGRAM_APP_ID` | yes, unless `META_APP_ID` is set |
| `INSTAGRAM_APP_SECRET` | yes, unless `META_APP_SECRET` is set |
| `INSTAGRAM_REDIRECT_URI` | no, if the public base is set |
| `META_APP_ID` / `META_APP_SECRET` | fallback for the Instagram and Facebook apps |
| `META_GRAPH_VERSION` | no. Default `v21.0` |

Create an app at https://developers.facebook.com/. Add Facebook Login and
the Instagram product. The Instagram account must be a business or creator
account linked to a Facebook Page.

Scopes: `instagram_basic`, `instagram_content_publish`, `pages_show_list`,
`pages_read_engagement`, `pages_manage_posts`, `business_management`.

Redirect URI: `{base}/social-studio/oauth/instagram/callback`.

Publishing is the container flow: `POST /{ig-user-id}/media` with
`image_url` or `video_url` (`media_type=REELS`), then
`POST /{ig-user-id}/media_publish`. The URL has to be public HTTPS. Meta
app review is required before anyone who is not an app admin, developer, or
tester can grant these permissions.
https://developers.facebook.com/docs/instagram-platform/content-publishing

### Facebook Pages

| Variable | Required |
| --- | --- |
| `FACEBOOK_APP_ID` | yes, unless `META_APP_ID` is set |
| `FACEBOOK_APP_SECRET` | yes, unless `META_APP_SECRET` is set |
| `FACEBOOK_REDIRECT_URI` | no, if the public base is set |

Same Meta app is fine. Scopes: `pages_show_list`, `pages_read_engagement`,
`pages_manage_posts`, `public_profile`.

Redirect URI: `{base}/social-studio/oauth/facebook/callback`.

Connect stores one account per Page, using that Page's access token.
Photos and videos are multipart uploads to `/{page-id}/photos` or
`/{page-id}/videos`. `privacy=private` sends `published=false`.
`pages_manage_posts` needs Meta app review for users outside app roles.
https://developers.facebook.com/docs/pages-api/posts

### X

| Variable | Required |
| --- | --- |
| `X_CLIENT_ID` | yes |
| `X_CLIENT_SECRET` | yes for a confidential client |
| `X_REDIRECT_URI` | no, if the public base is set |

Create a project and app at https://developer.x.com/. Turn on OAuth 2.0,
set the app type so the redirect can be saved, and enable the user-auth
scopes `tweet.read`, `tweet.write`, `users.read`, `offline.access`,
`media.write`.

Redirect URI: `{base}/social-studio/oauth/x/callback`.

The flow is OAuth 2.0 with PKCE (S256). Publish is
`POST /2/media/upload` then `POST /2/tweets`. Free, Basic, and Pro tiers
have different write caps. A 403 on create-post is the tier, not a silent
success. This adapter sends the media file in one upload call. Very large
chunked uploads are not implemented.
https://docs.x.com/x-api/posts/creation-of-a-post

### YouTube

| Variable | Required |
| --- | --- |
| `YOUTUBE_CLIENT_ID` | yes |
| `YOUTUBE_CLIENT_SECRET` | yes |
| `YOUTUBE_REDIRECT_URI` | no, if the public base is set |

In Google Cloud, enable YouTube Data API v3, configure the OAuth consent
screen, and create an OAuth client. Scopes:
`https://www.googleapis.com/auth/youtube.upload` and
`https://www.googleapis.com/auth/youtube.readonly`.

Redirect URI: `{base}/social-studio/oauth/youtube/callback`.

`youtube.upload` is a sensitive scope. An app that asks users outside the
test-user list needs Google's verification. The default quota is 10,000
units per day and `videos.insert` costs about 1,600 units, so a fresh
project can upload about six videos a day. The adapter uploads a video
with the resumable protocol and adds `#Shorts` to the description.
Still images raise `NotImplementedError`. Community posts are not in the
public Data API.
https://developers.google.com/youtube/v3/docs/videos/insert

### LinkedIn

| Variable | Required |
| --- | --- |
| `LINKEDIN_CLIENT_ID` | yes |
| `LINKEDIN_CLIENT_SECRET` | yes |
| `LINKEDIN_REDIRECT_URI` | no, if the public base is set |
| `LINKEDIN_ORGANIZATION_ID` | no. Set it to post as that organization |
| `LINKEDIN_REQUEST_ORG_SCOPE` | no. `true` adds `w_organization_social` to the consent screen |
| `LINKEDIN_API_VERSION` | no. Default `202410` |

Create an app at https://www.linkedin.com/developers/. Add the Share on
LinkedIn product for `w_member_social`. Member scopes requested: `openid`,
`profile`, `w_member_social`.

Redirect URI: `{base}/social-studio/oauth/linkedin/callback`.

Organization posting needs the Community Management API (or the current
organization social product) approved by LinkedIn, the
`w_organization_social` scope, and `LINKEDIN_ORGANIZATION_ID`. Image posts
call `POST /rest/images?action=initializeUpload`, PUT the bytes, then
`POST /rest/posts`. Video posts raise `NotImplementedError`. The Videos
API is a separate multi-part flow and is not wired up.
https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api

## What is implemented

| Platform | Connect and refresh | Images | Video |
| --- | --- | --- | --- |
| TikTok | yes | public HTTPS photo direct post. Unaudited apps forced to SELF_ONLY | file upload direct post |
| Instagram | yes, one account per linked professional account | container + `media_publish` (public URL) | reels container (public URL) |
| Facebook Pages | yes, one account per Page | multipart photo | multipart video |
| X | OAuth 2.0 PKCE | media upload + post | single-shot media upload + post |
| YouTube | yes | **not implemented** (Data API has no still-image post) | resumable Shorts upload |
| LinkedIn | yes, member or organization | initializeUpload + Posts API | **not implemented** |

Not implemented, on purpose, with `NotImplementedError` rather than a fake
permalink:

- YouTube stills and community posts
- LinkedIn video
- TikTok photo byte upload (the photo API is URL pull)
- Instagram byte upload, carousels, and stories
- Facebook Reels and stories
- X chunked upload for very large files, polls, and threads

`/social-studio/setup.json` reports which platforms have their client id
and secret set. It never includes the secret values.
