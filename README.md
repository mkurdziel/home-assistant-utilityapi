# Home Assistant UtilityAPI Integration

Custom integration for Home Assistant to connect to UtilityAPI (utilityapi.com).

Features:

- API key-based config flow
- Discovers meters that are not archived on load/reload
- Creates sensors per meter:
  - Last Update timestamp
  - Daily Usage (last completed day)
  - Daily Cost (last completed day)
- Uses a daily DataUpdateCoordinator to fetch last day's intervals and compute usage/cost
- Automatic backfill: 30-day lookback imported into Recorder external statistics (hourly usage and cost) so delayed UtilityAPI data is inserted at the correct timestamps.
- Configurable lookback: set days to backfill (1–365) in Options; default 30.

Setup:

- Copy `custom_components/utilityapi` into your Home Assistant `config/custom_components` folder.
- Restart Home Assistant.
- Add Integration > UtilityAPI, and enter your API key.

Notes:

- The integration polls daily. You can manually reload from the integration menu to force re-discovery of meters.
- The sensor's attributes include meter metadata (e.g., label, service address) when provided by the API.
- Daily Usage and Daily Cost represent the last fully completed local day. If intervals are unavailable for a meter, these sensors may show Unknown.
- Backfill is idempotent: when UtilityAPI makes older data available (e.g., weekly), the next daily run imports those hours retroactively. Statistics IDs used: `utilityapi:<meter_id>_usage` and `utilityapi:<meter_id>_cost`.

Manual backfill service:

- Service: `utilityapi.import_history`
- Fields:
  - `meter_id` (string): UtilityAPI meter ID
  - `start` (YYYY-MM-DD): start date inclusive
  - `end` (YYYY-MM-DD): end date exclusive
- Writes hourly usage (and cost if available) as external statistics with cumulative sums.

HACS Installation:

- In HACS → Integrations, add this repository as a Custom Repository with category `Integration`.
- Or, once published to HACS, search for "UtilityAPI" in HACS and install.
- After install, restart Home Assistant and add the UtilityAPI integration via the UI.

Releases:

- Tag the repo with a version (e.g., `v0.1.0`). Pushing a tag triggers a GitHub Release via workflow.
- HACS prefers installing from releases; keep semantic versioning.
