# DERLENG TV — Hostinger Business static deployment

Target: **https://tv.derlenghub.com**. Build tools run locally; shared hosting serves only static files. No Python, Node service, database, tunnel, paid upgrade or media proxy is required for the Mini App.

## Architecture

Browser → Hostinger static page/catalog → upstream HTTP/HTTPS HLS origins. Hls.js 1.7.4 is vendored locally with its license. Native HLS is supported where available. Telegram WebApp SDK remains an official remote script; fonts have system fallbacks.

The catalog is a **compatibility-filtered, unverified availability catalog**, not a guarantee that 5,975 channels work. HTTP and HTTPS HLS streams are accepted, including nonstandard ports. HTTPS browsers may block HTTP playback as mixed content; catalog/CSP acceptance does not override browser restrictions. DASH/other unsupported formats and unapproved URL parameters remain excluded. CORS on manifest, segment and key origins, codecs, redirects and regional availability still control playback. A Hostinger CORS header cannot repair an upstream's policy. No streaming/transcoding/relay runs on the Business hosting account.

Python polling bot and supervisor are **not deployed to Business hosting**. The Telegram global menu button can open this static Mini App even when the polling worker is off. Interactive bot commands need the separate Python worker; no new worker has been provisioned by this build.

## Build and validate

From this project directory:

```sh
python3 build_release.py
python3 -m unittest -v test_suite test_backend test_catalog_build
node test_frontend.cjs
```

Build output:

- `dist/hostinger/`: candidate web root, not project-root legacy HTML.
- `dist/derleng-tv-hostinger-<release-id>.zip`: **only this archive** is deployed.
- `dist/catalog-build-report.json`: exclusion counts (not public).
- `dist/latest-release.json`: selected archive/release.

The archive is deterministic, contains only 13 public files, excludes `.env`, raw catalog, source, logs and tests. `release-manifest.json` records SHA-256 hashes. `health.json` and `/healthz` are static release markers, not stream/bot readiness claims. `.htaccess` restricts served filenames, disables proxy, forbids private extensions/archives and directories, sets CSP allowing Telegram framing and hash-authorized application script, and applies cache policy. Do not add `X-Frame-Options: SAMEORIGIN/DENY` through hPanel/CDN: it can break Telegram Web.

Existing root `index.html`/`channels_public.json` are preserved legacy artifacts, not the deployment source. Edit `build_ui.py` and `catalog.py`, then build. The development server defaults to `dist/hostinger` and binds loopback:

```sh
python3 server.py --port 8080
```

No deployment command is run by either build or tests. Install browser tests with `npm ci` and `npx playwright install chromium`, then run `npm test`. `PLAYWRIGHT_MODULE` optionally selects an existing local installation.

## Hostinger deployment

1. Verify existing active Business order and exact target site through hPanel or official API.
2. Create **separate** empty `tv.derlenghub.com` website on the existing plan, not the parent domain's root. Wait for provisioning `completed`.
3. Read the exact TV document root and current files. Never overwrite another application. For later releases, obtain a rollback archive of current TV contents before replacing them.
4. Upload the generated archive with hPanel File Manager or the documented TUS upload API. Hostinger static deploy replaces this site's contents: use only the verified TV root.
5. If replacing a release on LiteSpeed, refresh ZIP entry timestamps in the deployment copy (without changing file bytes) and clear the site cache. Fixed build timestamps can leave old rules/headers cached; verify the current CSP hash and versioned catalog before declaring completion.
6. Verify TLS is active for the exact hostname; then enable HTTPS redirect. Existing nameservers need not be changed. Inspect DNS and modify only the TV record if automatic setup does not create it.
7. Verify `/`, `/release-manifest.json`, `/health.json`, versioned catalog, local HLS and assets. Compare all served bytes to the manifest. Check `/.env`, `/bot.py`, `/channels.json`, arbitrary files and uploaded ZIP cannot be downloaded; `/proxy` must not fetch anything.
8. Confirm Telegram Web framing, iOS/Android native playback/fullscreen and real channels. Automated Chromium is not certification of physical Telegram clients.
9. Only after public verification, set Telegram menu to `https://tv.derlenghub.com`. Preserve prior URL for rollback. Do not start the old tunnel supervisor for this static production deployment.

## Optional bot worker

Use a supported Python release (3.11+ recommended), keep `.env` private (0600), set `TELEGRAM_WEBAPP_URL=https://tv.derlenghub.com`, and deploy the matching published `channels_public.json` alongside the worker. Default path is `dist/hostinger/channels_public.json`; `DERLENG_CATALOG_FILE` overrides it. Run `python3 bot.py` under the existing worker's proper process manager. Do not run multiple pollers for one token. No raw stream URL is placed in bot links; they use `?cid=<stable-id>`.

Polling delivery is not exactly-once: persistent cursor/outbox/idempotency remains deferred. API timeouts are not blindly retried for side-effecting messages. Rate-limit retries are bounded. The optional supervisor now reports DNS/permission/TLS failures truthfully; it is a development/legacy component, not the Hostinger deployment dependency.

## Rollback

Restore the previous tested static archive to the **TV site only**, then verify its release manifest and TLS. Keep catalog, index, .htaccess and vendor version from one release together. Versioned filenames prevent mixed catalog reads; for zero-downtime future updates upload immutable assets first and switch the index last, or use a hosting-supported atomic release mechanism. Hostinger archive replacement has a deployment window and is not claimed atomic. Do not restore the old unrestricted proxy.

## Official references checked November 10, 2026

- https://www.hostinger.com/support/which-programming-languages-and-frameworks-are-supported-at-hostinger/
- https://www.hostinger.com/support/node-js-hosting-options-at-hostinger/
- https://developers.hostinger.com/openapi/openapi.json

The actual Business plan was verified through the existing authenticated account API. Public deployment evidence/status is recorded separately; this guide alone is not proof of live deployment.
