# Cambodian channel discovery — 2026-11-10

Research-only findings. Parent task performs browser/live tests before app import. No app files or hosting changed by this research task.

## Files

- `cambodia_candidates.json`: 12 current iptv-org KH directory sources not already present by exact URL. Bayon is an alternate for an existing identity, not another station.
- `cambodia_deeper_candidates.json`: 13 additional public URLs from broader research; known failures retained as research evidence, **not an import playlist**.
- `cambodia_deeper_probes.json`: response/HLS/CORS probes for those 13.
- `cambodia_legacy_probes.json`: 21 legacy public source checks, of which 20 failed (403, timeout, refused); the sole responding WIKI TV endpoint conflicts with another directory's TV3 identity.
- Downloaded HTML/source snapshots are retained alongside this report.

## Strong leads

1. **SEA TV** — official https://www.seatv.com.kh embeds `https://seatv.netlinkbroadcaster.com/hls/test.m3u8` directly. This independently corroborates the iptv-org URL and station identity.
2. **BTV News** — iptv-org publishes `https://live-evg2.tv360.metfone.com.kh/livetest/bayontest.stream/playlist.m3u8`. Parent handles full playback test. Do not confuse BTV with existing Bayon TV feed: they are distinct station identities.
3. **Fresh News HTTPS alternative** — `https://web-streaming.freshnewsasia.com/live/ngrp:myStream_all/playlist.m3u8` returned 200 HLS with `Access-Control-Allow-Origin: *`. Public source https://zuiai.tv/i/2320 (dated December 2025). Existing Fresh News identity, not a new channel. Potential replacement for existing HTTP relay source **only after complete playlist/segment and browser validation**. Official main site returned 403, so official-page linkage was not established by this run.

## Explicit exclusions / unresolved identities

- CTN/MyTV/CNC/CTV8/TV5 legacy HappyWatch sources failed DNS resolution. No hostname substitution or access-control bypass performed.
- iptv-org explicitly marks CTN, D Music and Komsan as not 24/7; these should not be represented as always-available verified additions.
- MSJ TV directory specifies a Referer. Browser compatibility requires independent no-header playback qualification; do not assume directory presence proves direct compatibility.
- `http://206.189.93.160:1935/live/myStream_720p/playlist.m3u8` responds, but directory https://zuiai.tv/i/2320 calls it TV3 while https://github.com/ArryH/KhmerIPTV/blob/master/Khmer.m3u8 calls same host/path WIKI TV; another public BeeTV gist calls it KIWI TV. **Do not add as TV3 without visible broadcaster identification.** May be an alternate of existing Wiki TV.
- Hang Meas `hmcine` HTTP endpoint responds, but the existing catalog already has HangMeasHDTV.kh. iptv-org issue https://github.com/iptv-org/iptv/issues/30140 names it Hang Meas Cine yet assigns that ID. Identity remains ambiguous; do not count it as a new station solely because its path differs.
- Rasmey Hang Meas clive endpoint returned 404; MOI TV connection refused; historic PNN 203.176.130.123 endpoint timed out.
- Current Free-TV master https://raw.githubusercontent.com/Free-TV/IPTV/master/playlist.m3u8 contained no Cambodian entries in the downloaded snapshot.
- iptv-org KH regional list includes MNB World, but it is Mongolian (`MNBWorld.mn`), not Cambodian. Country availability is not country of origin; it was excluded from Cambodian candidates.

## Official-site research

- https://www.cnc.com.kh loaded and embeds a Facebook video, not a public HLS source. Official site supports Cambodian identity but no compatible permanent HLS URL found.
- https://www.ctn.com.kh and https://www.mytv.com.kh returned 403.
- https://www.pnn.com.kh returned 412. https://tvonline.bg/watch-pnn-tv-live-from-cambodia/ points to broadcaster Facebook videos rather than an HLS feed.
- https://btv.com.kh returned 403.
- https://www.seatv.com.kh loaded and yielded the exact HLS source above.
- https://wtv.akctv.com.kh/WTV/ lists many Cambodian services in web-search results, but TLS certificate verification failed locally; HTTP timed out. No certificate checking was disabled and no unverified API inferred.
- Hang Meas official historical domains were unavailable, timed out or returned non-stream pages. Public social videos are not durable m3u8 streams and were not scraped for ephemeral tokens.

## Compatibility

New sources need browser advancing-video checks, fresh/live playlist checks and visible content confirmation. HTTP requires app relay routing via catalog ID and same-host segment restrictions; HTTP response 200 is insufficient. Distinguish scheduled source, regional blocks, incorrect branding and stale playlists from codec/player failure.

## Integration outcome
The parent checked playlists and media resources, not just HTTP status. The nine new HTTPS directory
links failed (404, DNS or TLS); all three HTTP directory candidates returned404.
Of the deeper leads, Hang Meas Cine's master responded but a nested resource returned404.
Fresh News HTTPS passed resource/CORS checks, two real Chromium advancing-frame/live-sequence
tests and visual review (FN station branding). It is now the preferred source for the existing
Fresh News stable ID; application retries can use its original HTTP relay.
The alleged TV3 IP stream passed video tests but showed educational content without adequate
station identity confirmation; conflicting Wiki/Kiwi attribution prevents adding it as TV3.
No genuinely new station was added. Catalog remains6064; Cambodia-origin entries remain14.
No paywall, login, TLS or header restriction was bypassed.
