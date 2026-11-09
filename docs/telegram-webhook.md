# Hostinger Telegram webhook

Production endpoint: `https://tv.derlenghub.com/bot-webhook.php`.
Same `@derlengtvbot`, Mini App URL, categories, eight-row pagination and stable `?cid=` links.
The handler uses PHP/cURL, not a persistent Python/Node process. `bot-menu.json` supplies category labels/order; counts and channel pages come from `channels_public.json`.

## Private configuration

`../.derleng-tv-bot/config.json`, relative to the public website root, holds `token` and `secret`. Parent directory mode 0700 and file 0600. Neither secret belongs in Git, the web archive, public logs or a URL. The temporary installer is omitted from the final archive and denied by final .htaccess. Do not re-enable it routinely.

Incoming POSTs require Telegram's `X-Telegram-Bot-Api-Secret-Token` header. Non-POST405, missing/wrong secret403, malformed update400 and oversized body413. Only private-chat commands/callbacks are handled. Webhook configuration: `max_connections=1`, `allowed_updates=[message,callback_query]`, never drop pending updates during cutover.

## Delivery state

A private flock-protected atomic `receipts.json` records per-update results for 48 hours, including successful message IDs. Concurrent requests get503 to retry; completed updates are not replayed. API429/retryable failures are bounded to 5 attempts and honor retry_after. Expired callback acknowledgements do not block actual menu delivery. Definite banner rejection400 falls back to text.

Ambiguous network timeout or crash after dispatch is recorded uncertain and is not blindly resent. This avoids duplicate sends but can leave a request unanswered: exactly-once delivery is not claimed. Operators should inspect private receipt statuses when diagnosing missed replies. No message bodies/token URLs are logged.

## Deployment and rollback

Build with `python3 build_release.py`; deploy the coherent archive including webhook PHP and bot-menu JSON. Preserve the private directory outside public_html. Use the updated task helper at workspace `outputs/tv-webhook-20261110/deploy.py`, which explicitly permits the webhook PHP file. The older relay-only helper rejects it.

Check `getWebhookInfo` (URL, pending updates, errors) using approved credentials; never print the token. Telegram stops getUpdates polling while a webhook is set.

The Mac LaunchAgent `com.derleng.tv-bot` is preserved but disabled/booted out at cutover. It must not be started alongside the webhook. Rollback order: call `deleteWebhook` with `drop_pending_updates=false`, enable the LaunchAgent and bootstrap its preserved plist. If restoring the prior static archive, first switch delivery back; that archive has no webhook handler. Do not delete the private config/receipts during normal rollback.

## Validation

Hostinger PHP 8.3.36/cURL: 57 preview/parity fixtures, menu delivery, category callback delivery despite expired ack, repeated and concurrent update suppression, out-of-order receipt recording, invalid-header/body and private-file denial checks. Existing 27 Python + 19 browser tests remain passing. Final cutover/live delivery results are recorded in workspace evidence and NeangCore handover.

## In-place channel selection (2026-11-10)
New category rows use `pick_<cid>` callbacks, not Mini App launch buttons. The
webhook validates the private chat/from identity and catalog ID, then atomically
stores the newest update in private `.derleng-tv-bot/selections/<uid>.json`.
`bot-selection.php` validates Telegram's signed initData (24-hour auth lifetime,
60-second future skew) before returning that user's selection (15-minute TTL).
The active Mini App polls every five seconds and on resume. Duplicate versions,
older explicit-link selections and selections predating a local click do not
restart/override playback. Hidden/deactivated views defer switching until resumed.

Telegram controls window foregrounding: callbacks cannot force an existing iOS
WebView to reopen. Users return to their open Mini App. When no recent heartbeat
exists, the bot attempts to send an explicit Open TV launch fallback. Selection is
saved before this optional notification; delivery of the hint is not guaranteed.
Old sent bot messages retain old launch buttons: request `/start` and reopen the
Mini App once after upgrading. Browser-only sessions have no Telegram identity
and do not poll. Expired authentication stops sync without interrupting video;
close/reopen the Mini App to refresh it. Multiple open views for the same Telegram
user can read the same selection; this is not an exclusive single-window API.

Deploy `bot-selection.php` and `bot-webhook.php` together using the release builder.
The Mac poller remains disabled. Private selections contain IDs/timestamps, not
initData or tokens. Do not expose this directory or accept a client-supplied user ID.
