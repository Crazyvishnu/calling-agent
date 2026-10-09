# Business discovery: OpenStreetMap

The dashboard now searches permitted OpenStreetMap data through the public Overpass
API. It finds business prospects, shows source records and website metadata, and
imports only selected, reviewed records. **Google Maps/Google Places is not connected.**
No credentials, paid account, billing service, scraping or customer outreach is activated.

## Use it

Run the existing backend and frontend using the README instructions; no additional
Python/npm dependency, speech model, Docker service or API key is required for discovery.
Internet is required for an explicit search. Open **Business discovery** in the sidebar.

1. Choose Hyderabad, Secunderabad, Gachibowli, Kukatpally or Banjara Hills. The preset
   fills coordinates. Alternatively enter another Indian location's coordinates and
   a descriptive label. Changing the label alone does **not** geocode an address.
2. Choose Restaurant, Cafe, Hotel, Retail shop, Salon, Clinic or School, then a radius
   of 500 metres to 5 km. The API also accepts radii down to 250 metres.
3. Click **Search businesses**. Check the names, addresses and OpenStreetMap source
   links. Use **Website not listed** to prioritize records for manual research.
4. Select up to 20 records, confirm that you reviewed them, then import. Imported
   prospects appear in **Lead directory** with source attribution and observation time.
5. Separately verify contact permission and its evidence before any conversation/call.
   Research records are not approved calling contacts. No automatic outreach follows.

## What the website signal means

- **Listed**: OSM contains a usable HTTP/HTTPS website tag. This is not proof of
  business ownership, availability, freshness, design quality or security.
- **Not listed**: the record contains no website tag. The business may still have a
  website, social profile or ordering platform. Never advertise this as “no website”.
- **Needs review**: a website tag exists but could not be presented as a safe link.

The system does not crawl business websites or grade them. External links open only
when you choose them. There is no map-tile viewer, automatic geocoder, background
scanner, email outreach, phone verification or Google Maps scraping.

## Search bounds, storage and deduplication

Search sends only coordinates, radius and category to `https://overpass-api.de`.
The backend builds a fixed query; callers cannot supply an endpoint or arbitrary
Overpass syntax. Queries request at most 100 results with a 20-second upstream
execution limit; client timeout is 30 seconds and response size is bounded. Coverage
is incomplete, results are not necessarily the closest 100 businesses, and some
business categories are represented by approximate OSM tags.

The single-process development server allows at most one new upstream search per
minute and caches identical searches for 15 minutes. At most 16 searches remain in
memory. Expired searches cannot be imported; cache entries are removed on a subsequent
search or server stop. No raw search JSON is written to SQLite. Provider errors or
partial query results report an error instead of pretending there are no businesses.
Public community services have no availability guarantee; repeated unattended or
large-scale use requires reviewing their policies and suitable infrastructure.

Imports use identifiers from the server's search cache, not edited client records.
They preserve source ID/URL/time and attribution, start with contact permission false
and blank consent evidence, and never change existing lead status or suppression.
Duplicates are checked using OSM identity, normalized phone, exact normalized website,
or normalized business name plus city. Indian +91/leading-zero phone formats are
handled. Matching a shared phone/website can conservatively skip another branch;
different names/numbers can miss a duplicate. Human review remains necessary.
If OSM lists multiple phone numbers, this prototype keeps the first one.

Reviewed imported records are stored in the existing private SQLite database. Keep it
and backups out of public GitHub. This milestone adds provenance columns and a unique
source index without replacing existing leads. It does not independently establish
that storing/contacting a particular person is appropriate.

## Attribution and licenses

Business source data is **© OpenStreetMap contributors**, licensed under
**ODbL 1.0**: <https://www.openstreetmap.org/copyright>.
Attribution is displayed on results, stored on imported records and shown in lead
details. OSM data and your application code have separate licenses. Before publicly
distributing an exported/derived database, assess ODbL attribution and share-alike
obligations; do not remove provenance or claim ownership of OSM data.

A future Google Places adapter would require checking credentials, billing setup,
quotas, current terms and restrictions on caching/storage/attribution. It must not
reuse the OSM permanent-import rules for Google content. No paid activation will
happen without explicit approval. Publicly discoverable contact information still
does not authorize automated promotional calling.

## API and verification

- `GET /api/discovery/config`: presets, categories, limits and attribution.
- `POST /api/discovery/search`: location label, latitude, longitude, category, radius_m.
- `POST /api/discovery/import`: search_id, selected keys and `reviewed: true`.

`422`: invalid query/selection/review. `429`: wait before another new search.
`410`: search expired; rerun it. `503`: public source unavailable/incomplete.
Keep this unauthenticated prototype bound to loopback and use one Uvicorn worker.

Verified in this Linux workspace: live OSM search returned 10 restaurant records
within the central Hyderabad query (9 website tags absent); live browser → API →
OSM displayed 10 records without importing any. Browser → API → SQLite import was
tested with fictional provider fixtures, including the website filter, source metadata,
duplicate disabling and blocked conversations. No real business was contacted.
The backend suite passes 48 tests and the frontend builds. Windows discovery execution
is not yet verified. See [verification history](VERIFICATION.md).
