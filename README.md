# DERLENG TV

Khmer-first Telegram Mini App and standalone web TV player, deployed as a static HTTPS website on **Hostinger Business Web Hosting**.

**Live:** https://tv.derlenghub.com · **Source:** https://github.com/neangneatos/derleng-tv

## Current live version

Verified November 10, 2026 (Asia/Phnom_Penh):

- Release: `bffaaeb5949218f4`
- Catalog version: `7cf4130f51b8af05`
- **5,169 published channel entries**, confirmed by downloading the live catalog.
- Downloadable public assets match the live release manifest's SHA-256 hashes.
- Catalog inclusion means a compatible URL candidate, **not verified working playback**.

### Why fewer than 6,000 channels?

The original local input contained **6,172 records**. The static-release policy excluded **1,003**, leaving **5,169**:

| First rejection reason | Entries |
| --- | ---: |
| Non-HTTPS stream URL | 395 |
| Nonstandard port | 442 |
| Unsupported stream format/path (not `.m3u8`) | 73 |
| Unapproved URL query parameters | 80 |
| Private URL form | 6 |
| Invalid channel name | 7 |
| **Total excluded** | **1,003** |

These counts describe policy filtering, not 1,003 confirmed dead channels. In particular, nonstandard-port URLs might work elsewhere but are deliberately excluded by this release policy. Do not simply re-enable rejected URLs to advertise “6,000+ working channels.” See [original build counts](docs/original-catalog-build-report.json).

The committed `channels.json` is the **already sanitized public snapshot**, not the original raw input. It reproduces the same live catalog and release; a fresh build therefore reports 5,169 published and zero rejected. Rejected/private URLs are intentionally not published here.

The UI initially embeds a small bootstrap selection, then fetches the full versioned catalog. A category, search filter, or failed full-catalog download can show fewer results than the total. Clear filters and check that the versioned catalog request succeeds before treating the visible count as the total.

## Architecture and features

```text
Telegram WebView / browser
        |
        v
Hostinger: HTML + catalog + Hls.js + static assets
        |
        v
Third-party HTTPS HLS stream origins (direct playback)

Optional separate Python polling worker -> Telegram Bot API
```

- Khmer UI, categories/search, progressive channel rendering and stable `?cid=<channel-id>` links.
- Hls.js 1.7.4 with native HLS fallback; bounded recovery and playback-progress checks.
- One sanitized catalog shared by the Mini App and optional bot.
- No public stream proxy, transcoder, database or tunnel required.
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
- `dist/derleng-tv-hostinger-<release-id>.zip` — deterministic static-only upload archive.
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

The current revision passes **23 Python tests and 9 synthetic Chromium scenarios** locally. Synthetic scenarios do not establish real upstream playback. CI builds/tests and uploads a release artifact; it does **not** deploy to Hostinger or change Telegram settings. The old optional `test_suite.py --benchmarks` path relies on a local historical snapshot and is not part of portable validation.

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
