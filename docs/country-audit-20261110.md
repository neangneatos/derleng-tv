# DERLENG TV country audit — 10 November 2026

## Frozen result

All **6,064 entries** audited individually. **4,909 have evidenced broadcaster/channel origin**; **1,155 remain origin-unverified**. Among the latter, **1,117 have a separately evidenced curated feed/service market**, and 38 have neither an unambiguous origin nor curated market. Never label a feed market as broadcaster origin. 140 previously unresolved entries gained origin evidence; 105 known-origin country values change. Two previously matched identities change based on stronger exact stream evidence: Faith TV US → Faith Africa ZA; NRB TV CA → NRB TV US.

43 earlier name-based country assignments now require review because their supposed broadcaster origin conflicts with the curated feed market and there is no exact stream-to-identity evidence. This conflict does **not** prove either country false: it is a reason not to assert origin. Examples include Euronews → Poland for a Norway feed, Auto TV → Brazil for a Mongolia feed, and Clan → Spain for a German feed. All such rows have `identity_caution` and `candidate_identity` fields; old tvg_id should not continue to imply verified identity for these rows.

## Sources and priority

1. Current iptv-org API channel records, including official broadcaster website references.
2. Exact URL in the current raw `iptv-org/iptv` streams repository, linked through its `tvg-id` to API origin country: 4,733 entries.
3. Earlier explicit identity mappings that are not in conflict with observed raw feed markets: 153 entries.
4. Unambiguous normalized names (quality/schedule suffix removed, channel numbers and `+`/`&` preserved): 13 entries; 2 ambiguous identities agreeing on country.
5. Eight reviewed broadcaster naming variants: Sony Sports Ten 4 Telugu, BBC Lifestyle Asia, DocuBox HD, Job Plus TV, TCT Network, Đồng Nai 2, Al Aoula Inter, Arryadia HD TNT. These are medium-confidence origin identifications, not playback or worldwide-availability certification.
6. Curated internal country/service playlists provide **feed-market evidence only**. Upstream `docs/playlists.md` explicitly says they are grouped for link moderation. Platform examples include Pluto, Samsung, Rakuten. Raw source grouping must not be interpreted as corporate headquarters or broadcaster nationality.

`country-sources/` retains downloaded channels/feeds API, raw repository archive, original playlist identifiers, original-URL match evidence, official-page snapshots and fetch status. Existing local originals covered all unresolved URLs but had no valid tvg IDs; they therefore cannot independently establish nationality. Official page checks succeeded for Jobplus, DocuBox, TCT and SNRT; Sony returned 502 and Dong Nai had invalid TLS. Failed requests were not treated as successful evidence.

## Output contract

- `country-audit-all.json` / `.csv`: exhaustive 6,064-entry ledger, including unchanged and unknown entries.
- `country-proposals.json`: URL-indexed **known-origin** proposals only (4,909).
- `country-corrections.json`: changed known-origin labels only (105).
- `country-unresolved.json`: 1,155 rows requiring `ZZ` / Unknown origin; 1,117 include `market_code` / `market_name`.
- `country-summary.json`: totals.

For integration use the exhaustive audit, not only corrections, so unsupported old labels are cleared. Use country `ZZ`, group `Unknown origin` for null `proposed_country`; preserve separately named market fields for useful display such as “France feed · origin unverified.” Do not silently keep earlier guessed country codes. Existing exact stream/API origins are preferred even when service market differs: 751 such differences are recorded, not treated as contradictions.

UK in upstream metadata is normalized to ISO `GB`. CDN geography, IP geolocation, domain suffix, content language and programme production country were never used alone to assign origin. A country's flag identifies origin only, not current geographic availability.

No application, deployment, source catalog, or Git changes were made by this audit. Source snapshots are time-bound; no claim that all worldwide metadata is perfectly correct is made.

## Applied integration
This frozen audit was applied to all6,064 records. Unknown origins use ZZ and are visibly distinguished
from feed-market evidence. Source data's UK code is normalized to GB and United Kingdom labels retained.
41 logo matches linked to withdrawn/changed identities were removed rather than retaining unproven branding.
Published totals:4,909 origin labels;1,117 market-only labels;38 fully unresolved.
27 Python tests and15 synthetic browser scenarios validate metadata preservation, labels and source fallback.
