"""Config flow for Remember Where I Parked."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_ADDRESS_SENSORS,
    CONF_BLUETOOTH_MAC,
    CONF_BLUETOOTH_SENSORS,
    CONF_PEOPLE,
    DOMAIN,
)
from .coordinator import normalize_mac


def _entity_options(hass, domains: tuple[str, ...]) -> dict[str, str]:
    """Build multi-select options from loaded states."""
    return {
        state.entity_id: state.name or state.entity_id
        for state in sorted(
            (
                state
                for state in hass.states.async_all()
                if state.domain in domains
            ),
            key=lambda state: state.entity_id,
        )
    }


class RememberWhereIParkedConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Remember Where I Parked."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Collect the car name and Bluetooth MAC address."""
        errors: dict[str, str] = {}

        if user_input is not None:
            normalized_mac = normalize_mac(user_input[CONF_BLUETOOTH_MAC])
            if normalized_mac is None:
                errors[CONF_BLUETOOTH_MAC] = "invalid_mac"
            else:
                await self.async_set_unique_id(normalized_mac)
                self._abort_if_unique_id_configured()
                self._data = {
                    "name": user_input["name"].strip(),
                    CONF_BLUETOOTH_MAC: normalized_mac,
                }
                return await self.async_step_people()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("name"): str,
                    vol.Required(CONF_BLUETOOTH_MAC): str,
                }
            ),
            errors=errors,
        )

    async def async_step_people(self, user_input: dict[str, Any] | None = None):
        """Collect the people that can drive the configured car."""
        people_options = _entity_options(self.hass, ("person",))
        errors: dict[str, str] = {}

        if not people_options:
            errors["base"] = "no_people"

        if user_input is not None and not errors:
            selected_people = list(user_input.get(CONF_PEOPLE, []))
            if not selected_people:
                errors[CONF_PEOPLE] = "required"
            else:
                self._data[CONF_PEOPLE] = selected_people
                return await self.async_step_sensors()

        return self.async_show_form(
            step_id="people",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PEOPLE): cv.multi_select(people_options),
                }
            ),
            errors=errors,
        )

    async def async_step_sensors(self, user_input: dict[str, Any] | None = None):
        """Collect Bluetooth and optional address sensors."""
        bluetooth_sensor_options = _entity_options(self.hass, ("sensor", "binary_sensor"))
        address_sensor_options = _entity_options(self.hass, ("sensor",))
        errors: dict[str, str] = {}

        if user_input is not None:
            bluetooth_sensors = list(user_input.get(CONF_BLUETOOTH_SENSORS, []))
            if not bluetooth_sensors:
                errors[CONF_BLUETOOTH_SENSORS] = "required"
            else:
                self._data[CONF_BLUETOOTH_SENSORS] = bluetooth_sensors
                self._data[CONF_ADDRESS_SENSORS] = list(
                    user_input.get(CONF_ADDRESS_SENSORS, [])
                )
                return self.async_create_entry(
                    title=self._data["name"],
                    data=self._data,
                )

        return self.async_show_form(
            step_id="sensors",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_BLUETOOTH_SENSORS): cv.multi_select(
                        bluetooth_sensor_options
                    ),
                    vol.Optional(CONF_ADDRESS_SENSORS, default=[]): cv.multi_select(
                        address_sensor_options
                    ),
                }
            ),
            errors=errors,
        )
