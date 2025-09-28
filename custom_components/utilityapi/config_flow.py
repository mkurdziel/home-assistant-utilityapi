from __future__ import annotations

from typing import Any, Dict

import hashlib
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, CONF_API_KEY
from .api import UtilityAPIClient, InvalidAuthError, UtilityAPIError


class UtilityAPIConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return UtilityAPIOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        errors: Dict[str, str] = {}
        if user_input is not None:
            api_key = user_input.get(CONF_API_KEY, "").strip()
            if not api_key:
                errors["base"] = "invalid_auth"
            else:
                session = async_get_clientsession(self.hass)
                client = UtilityAPIClient(session, api_key)
                try:
                    await client.validate()
                except InvalidAuthError:
                    errors["base"] = "invalid_auth"
                except UtilityAPIError:
                    errors["base"] = "cannot_connect"
                else:
                    unique = hashlib.sha256(api_key.encode()).hexdigest()[:12]
                    await self.async_set_unique_id(f"utilityapi_{unique}")
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(title="UtilityAPI", data={CONF_API_KEY: api_key})

        data_schema = vol.Schema({vol.Required(CONF_API_KEY): str})
        return self.async_show_form(step_id="user", data_schema=data_schema, errors=errors)


class UtilityAPIOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        # No options for now, just provide a way to trigger reload
        return self.async_create_entry(title="Options", data={})

