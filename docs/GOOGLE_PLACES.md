# Optional Google Maps research

The application includes an **IDs-only Google Places (New) Text Search adapter**, with owner authorization, explicit per-request cost acknowledgement and a persisted rolling 24-hour request cap. It is disabled by default. The owner reported having no Google API access or approved billing, so **no live Google request was made**.

The dashboard provides result links to Google Maps. It does not scrape Maps or copy names, telephone numbers, reviews, ratings or website information into CRM. Returned identifiers/links exist only in the response and current UI, without backend caching. There is no Google-result import endpoint. Manually obtained, independently licensed or customer-provided requirements can still be entered through the ordinary CRM workflow with documented consent.

The field mask is exactly `places.id`; changing fields can change the SKU and cost. Official policy exempts place IDs from caching restrictions, but this implementation does not persist returned IDs either. UI results show Google attribution. Review [Places policies](https://developers.google.com/maps/documentation/places/web-service/policies), [billing](https://developers.google.com/maps/documentation/places/web-service/usage-and-billing), required public terms/privacy disclosures and current India pricing before activation.

Activation requires the owner to obtain/restrict a server-side API key, explicitly approve billing, review terms and set private environment variables:

```dotenv
GOOGLE_PLACES_ENABLED=1
GOOGLE_PLACES_API_KEY=your-private-server-key
GOOGLE_PLACES_BILLING_APPROVED=1
GOOGLE_PLACES_TERMS_REVIEWED=1
GOOGLE_PLACES_DAILY_LIMIT=3
```

Do not enable these settings until those steps are actually completed. The app caps the configured limit at ten requests per rolling 24 hours, reserves before network I/O, counts failed/uncertain requests and never retries automatically. This is an application request cap, **not a monetary spending guarantee** across the Google account or other applications. Configure provider-side quotas/restrictions and monitor billing. Google trials/free allowances are not permanent unlimited service guarantees.

Routes: `GET /api/google-places/status`; owner-only `POST /api/google-places/search` with `{"query":"Restaurants in Hyderabad","cost_acknowledged":true}`. HTTP tests mock Google and cover disabled state, role/cost gates, exact fields, bounded results, no CRM import, persisted quota and sanitized failures. Live API and billing behavior remain unverified until the owner provides approved access.
