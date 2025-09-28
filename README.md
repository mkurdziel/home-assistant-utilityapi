# Home Assistant UtilityAPI Integration

Custom integration for Home Assistant to connect to UtilityAPI (utilityapi.com).

Features:

- API key-based config flow
- Discovers meters that are not archived on load/reload
- Creates a sensor per meter reporting the meter's last update timestamp
- Uses a daily DataUpdateCoordinator to check for new data for each meter

Setup:

- Copy `custom_components/utilityapi` into your Home Assistant `config/custom_components` folder.
- Restart Home Assistant.
- Add Integration > UtilityAPI, and enter your API key.

Notes:

- The integration polls daily. You can manually reload from the integration menu to force re-discovery of meters.
- The sensor's attributes include meter metadata (e.g., label, service address) when provided by the API.

HACS Installation:

- In HACS → Integrations, add this repository as a Custom Repository with category `Integration`.
- Or, once published to HACS, search for "UtilityAPI" in HACS and install.
- After install, restart Home Assistant and add the UtilityAPI integration via the UI.

Releases:

- Tag the repo with a version (e.g., `v0.1.0`). Pushing a tag triggers a GitHub Release via workflow.
- HACS prefers installing from releases; keep semantic versioning.
