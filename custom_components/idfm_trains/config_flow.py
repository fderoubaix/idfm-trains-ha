"""Config flow for IDFM Trains integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_API_KEY,
    CONF_LINES_FILTER,
    CONF_OUTSIDE_INTERVAL,
    CONF_STOP_AREA_ID,
    CONF_STOP_NAME,
    CONF_TIME_END,
    CONF_TIME_START,
    CONF_TRAIN_COUNT,
    CONF_UPDATE_INTERVAL,
    DEFAULT_OUTSIDE_INTERVAL,
    DEFAULT_STOP_AREA_ID,
    DEFAULT_STOP_NAME,
    DEFAULT_TIME_END,
    DEFAULT_TIME_START,
    DEFAULT_TRAIN_COUNT,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    KNOWN_LINES,
    STOP_MONITORING_URL,
)

_LOGGER = logging.getLogger(__name__)


async def _validate_api_key(hass, api_key: str, stop_area_id: str) -> str | None:
    """
    Test the API key against the PRIM API.
    Returns None on success, or an error string on failure.
    """
    monitoring_ref = f"STIF:StopArea:SP:{stop_area_id}:"
    headers = {"apiKey": api_key, "Accept": "application/json"}
    session = async_get_clientsession(hass)
    try:
        async with session.get(
            STOP_MONITORING_URL,
            params={"MonitoringRef": monitoring_ref},
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status == 401:
                return "invalid_api_key"
            if resp.status == 404:
                return "invalid_stop_area"
            if resp.status not in (200, 204):
                return "cannot_connect"
    except aiohttp.ClientError:
        return "cannot_connect"
    return None


class IdfmTrainsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow for IDFM Trains."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Step 1 – API key + stop configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            stop_area_id = user_input[CONF_STOP_AREA_ID].strip()
            stop_name = user_input.get(CONF_STOP_NAME, DEFAULT_STOP_NAME).strip()

            error = await _validate_api_key(self.hass, api_key, stop_area_id)
            if error:
                errors["base"] = error
            else:
                # Prevent duplicate entries for the same stop
                await self.async_set_unique_id(f"{DOMAIN}_{stop_area_id}")
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"IDFM – {stop_name}",
                    data={
                        CONF_API_KEY: api_key,
                        CONF_STOP_AREA_ID: stop_area_id,
                        CONF_STOP_NAME: stop_name,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY): str,
                vol.Required(
                    CONF_STOP_AREA_ID, default=DEFAULT_STOP_AREA_ID
                ): str,
                vol.Optional(
                    CONF_STOP_NAME, default=DEFAULT_STOP_NAME
                ): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "prim_url": "https://prim.iledefrance-mobilites.fr",
                "default_stop": f"Achères-Ville (ZdA ID: {DEFAULT_STOP_AREA_ID})",
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> IdfmTrainsOptionsFlow:
        return IdfmTrainsOptionsFlow(config_entry)


class IdfmTrainsOptionsFlow(config_entries.OptionsFlow):
    """Options flow (accessible via Configurer)."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Options form."""
        opts = self._entry.options

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        line_choices = {lid: info["name"] for lid, info in KNOWN_LINES.items()}

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_TRAIN_COUNT,
                    default=opts.get(CONF_TRAIN_COUNT, DEFAULT_TRAIN_COUNT),
                ): vol.All(int, vol.Range(min=1, max=10)),
                vol.Optional(
                    CONF_UPDATE_INTERVAL,
                    default=opts.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
                ): vol.All(int, vol.Range(min=1, max=60)),
                vol.Optional(
                    CONF_OUTSIDE_INTERVAL,
                    default=opts.get(CONF_OUTSIDE_INTERVAL, DEFAULT_OUTSIDE_INTERVAL),
                ): vol.All(int, vol.Range(min=5, max=120)),
                vol.Optional(
                    CONF_TIME_START,
                    default=opts.get(CONF_TIME_START, DEFAULT_TIME_START),
                ): str,
                vol.Optional(
                    CONF_TIME_END,
                    default=opts.get(CONF_TIME_END, DEFAULT_TIME_END),
                ): str,
                vol.Optional(
                    CONF_LINES_FILTER,
                    default=opts.get(CONF_LINES_FILTER, []),
                ): vol.All(
                    [vol.In(line_choices)],
                ),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
