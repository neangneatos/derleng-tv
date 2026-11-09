# DERLENG TV

Khmer-first Telegram Mini App and standalone web TV player, deployed as an HTTPS website with a bounded PHP HLS relay on **Hostinger Business Web Hosting**.

**Live:** https://tv.derlenghub.com · **Source:** https://github.com/neangneatos/derleng-tv

## Current live version

Verified November 10, 2026 (Asia/Phnom_Penh):

- Release: `8462f86d358ad0fd`
- Catalog version: `49b3c49010de3067`
- **6,064 published channel entries: 5,699 HTTPS and 365 HTTP.**
- Both HTTP and HTTPS HLS URLs are accepted; explicit nonstandard ports are preserved.
- Catalog inclusion is **not verified working playback**. HTTP HLS channels are fetched through the same-origin HTTPS `relay.php` endpoint; HTTPS channels remain direct. This avoids HTTP mixed-content requests from the browser. Upstream failures, formats and origin restrictions can still prevent playback. Fresh News was browser-playback-tested; the entire catalog is not certified.

### Categories and broadcaster logos

The 89 additions were previously qualified by two browser playback checks, playlist advancement and visual review. This does not certify the older catalog or future availability.

All Channels is beside Cambodia, followed by 12 genre tabs: Kids, Sports, News, Movies, Documentary, Music, Education, Religious, Business, Lifestyle, Entertainment and General. Empty genre tabs hide; country and genre remain separate. Matched iptv-org metadata corrects default classifications; ambiguous identities retain their prior metadata.

Broadcaster logos are validated raster images, resized to small content-addressed WebP files under `logos/`, and served locally over HTTPS. Lazy loading avoids thousands of image requests on startup. Image failures and unmatched identities use channel initials, not broken images or invented broadcaster logos. See [catalog enrichment](docs/catalog-enrichment-20261110.md) for coverage and provenance.

The loading overlay now waits for sustained lack of video progress; transient fetch stalls no longer cover advancing video.

### Catalog counts

The original local input contained **6,172 records**. Restoring HTTP/nonstandard-port sources recovered **806** entries compared with the first HTTPS-only release (5,169), producing 5,975. Adding 89 newly researched entries produces **6,064**. The local raw input now has 6,261 records; the same 197 policy exclusions remain:

| First rejection reason | Entries |
| --- | ---: |
| Unsupported stream format/path (not `.m3u8`) | 88 |
| Unapproved URL query parameters | 96 |
| Private URL form | 6 |
| Invalid channel name | 7 |
| **Total excluded** | **197** |

These are policy exclusions, not confirmed dead channels. Counts by reason changed because HTTP/port checks no longer reject entries before other validation runs. DASH and extensionless sources require separate player/source validation; credential-bearing URLs are not published. The historical first-release counts remain in [original build counts](docs/original-catalog-build-report.json).

The committed `channels.json` is the **sanitized public snapshot**, not the raw private input. A fresh build reports 6,064 published and zero rejected after adding 89 separately researched entries.

The UI initially embeds a small bootstrap selection, then fetches the full versioned catalog. A category, search filter, or failed full-catalog download can show fewer results than the total. Clear filters and check that the versioned catalog request succeeds before treating the visible count as the total.

## Architecture and features

```text
Telegram WebView / browser
        |
        v
Hostinger: HTML + catalog + Hls.js + PHP HTTP-HLS relay
        |
        v
HTTPS origins: direct playback
HTTP origins: fetched server-side by the HTTPS relay

Optional separate Python polling worker -> Telegram Bot API
```

- Khmer UI, categories/search, progressive channel rendering and stable `?cid=<channel-id>` links.
- Hls.js 1.7.4 with native HLS fallback; bounded recovery and playback-progress checks.
- One sanitized catalog shared by the Mini App and optional bot.
- Restricted PHP HLS relay for HTTP channels; no transcoder, database or tunnel required.
- Generated `.htaccess` restricts public files, disables `/proxy`, and provides security/cache headers.
- `/health.json` and `/healthz` indicate a static release is present; they do not certify streams or the bot.

Hostinger serves the **Mini App**, not the Python bot or supervisor. Interactive bot commands require a separate supported Python worker. Streaming depends on upstream CORS, codecs, connectivity, region restrictions and availability. Only use streams you are authorized to access/distribute.

## Quick start

Python 3.11+ is recommended. The build, preview and Python tests use the standard library; no pip packages are required.

```sh
git clone https://github.com/neangneatos/derleng-tv.git
cd derleng-tv
python3 build_release.py
python3 server.py --port 8080
```

Open http://127.0.0.1:8080. Serve over HTTP rather than opening HTML as a local file.

### Build outputs

- `dist/hostinger/` — complete deployable website.
- `dist/derleng-tv-hostinger-<release-id>.zip` — deterministic web/PHP archive.
- `dist/latest-release.json` — selected release/archive.
- `dist/catalog-build-report.json` — current input's filtering results.

Edit `build_ui.py`, `catalog.py` and `channels.json`, then rebuild. Generated files are ignored by Git. The obsolete root `index.html` and old Jekyll deployment workflow have been removed from this repository; **do not upload the repository root**.

## Tests

```sh
python3 build_release.py
python3 -m unittest -v test_suite test_backend test_catalog_build

# Node.js 22+; browser tooling is development-only
npm ci
npx playwright install chromium
npm test
```

The current revision passes **25 Python tests and 13 synthetic Chromium scenarios** locally. Synthetic scenarios do not establish real upstream playback. CI builds/tests and uploads a release artifact; it does **not** deploy to Hostinger or change Telegram settings. The old optional `test_suite.py --benchmarks` path relies on a local historical snapshot and is not part of portable validation.

## Deploy to Hostinger Business

Follow [DEPLOY_HOSTINGER.md](DEPLOY_HOSTINGER.md) for detailed deployment, verification and rollback.

1. Build and test locally or download the tested CI artifact.
2. Back up the current **TV site's** public contents for rollback.
3. Upload/extract only the generated ZIP into the document root assigned to `tv.derlenghub.com`, including `.htaccess`. Do not touch another site's root.
4. Verify DNS and HTTPS for `tv.derlenghub.com`.
5. Check live manifest/hash matches, catalog count, real playback and Telegram framing. Private paths must be denied and `/proxy` must return 410.
6. Keep index, catalog, vendor assets and `.htaccess` from the same release together.

A GitHub push updates source and runs CI only. It does not automatically update the live Hostinger website.

## Optional Telegram worker

```sh
cp .env.example .env
chmod 600 .env
# Set TELEGRAM_BOT_TOKEN in .env; never commit it.
# Keep TELEGRAM_WEBAPP_URL and MINI_APP_URL at https://tv.derlenghub.com
python3 build_release.py
./run.sh
```

Run only one poller per token, on a separate always-on Python host. The worker defaults to `dist/hostinger/channels_public.json`; `DERLENG_CATALOG_FILE` can override this. `start_tv.py` is a legacy/development supervisor, not the production static-site launcher.

**Known unresolved items from deployment:** Telegram accepted the menu update but read-back still returned the previous tunnel URL; menu migration is not certified. No production polling worker was started by the static deployment. Physical Telegram iOS/Android validation and a 24-hour soak remain outstanding. Earlier live Chromium checks played EAC News and Apsara; TVK did not progress within the observation window. No all-channel availability guarantee is made.

## Next implementation priorities

1. Resolve and read back the Telegram menu URL; confirm actual device launch.
2. Qualify a smaller reliably playable channel set using timestamped region/device checks.
3. Review excluded URLs individually; add only supported, authorized, non-sensitive sources. Do not restore the unrestricted proxy.
4. Add automated scheduled catalog validation and freshness reporting, distinct from static-site uptime.
5. Complete physical-device/fullscreen checks and soak testing.
6. If interactive bot operations are needed, provision a separate worker with persistent cursor/idempotency and monitoring.

## Repository map

| Path | Purpose |
| --- | --- |
| `build_ui.py`, `catalog.py` | UI generation and URL/catalog policy |
| `build_release.py` | Static ZIP, manifest, CSP and hosting rules |
| `channels.json` | Public sanitized source snapshot |
| `server.py` | Loopback development preview |
| `bot.py`, `run.sh` | Optional external Telegram polling worker |
| `start_tv.py` | Legacy/development supervisor |
| `test_*.py`, `test_frontend.cjs` | Offline/synthetic regressions |
| `vendor/` | Pinned Hls.js and upstream license |
| `docs/` | Non-sensitive catalog audit counts |

Keep `.env`, credentials, logs, raw/private catalogs and hosting backups out of Git and out of the public web root. Hls.js retains its upstream license in `vendor/hls-LICENSE.txt`; this repository does not grant rights to third-party channel content.

## HTTP HLS relay

Hostinger runs `relay.php` with PHP/cURL; this is no longer a strictly static-only deployment. The PHP user must be able to create a private signing key and six lock files in the parent of the document root. No credentials are shipped in Git or the ZIP.

- Entry requests use a published HTTP channel ID, never an arbitrary URL. Nested playlist, segment and key URLs are signed. Catalog removal revokes access; signed URLs remain stable for long-running live playlists.
- Redirects/nested resources stay on the source hostname, with original/80/443 ports only. Public IPv4 destinations are validated and pinned, TLS verification remains enabled, and private/reserved addresses are denied. Cross-CDN resource hosts are intentionally unsupported until explicitly reviewed.
- Rewrites playlist URI lines and quoted URI attributes (variants, segments, audio, initialization maps and keys). Supports single byte ranges. Not a transcoder, DRM bypass or arbitrary-file proxy.
- Resource limits: six simultaneous upstream requests globally, 18-second request timeout, 16 MiB per resource, 1 MiB playlists, bounded redirects. Busy requests return 503. Shared-hosting capacity and bandwidth are not load-certified; this is not a promise of unlimited viewers.
- HTTP upstream traffic remains unencrypted between Hostinger and the broadcaster. The browser-to-Hostinger connection is HTTPS.
- `/proxy` remains disabled. `/relay.php?status=1` reports PHP/cURL availability only. Verify real advancing video time, not just a successful playlist response.
