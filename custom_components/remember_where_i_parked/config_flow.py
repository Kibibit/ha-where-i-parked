"""Config flow for Remember Where I Parked."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import State
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_BLUETOOTH_MAC,
    CONF_ENABLE_HIGH_ACCURACY_MODE,
    CONF_HIGH_ACCURACY_MODE_POLICY,
    CONF_HIGH_ACCURACY_UPDATE_INTERVAL,
    CONF_PEOPLE,
    CONF_PHONE_TRACKERS,
    DEFAULT_ENABLE_HIGH_ACCURACY_MODE,
    DEFAULT_HIGH_ACCURACY_MODE_POLICY,
    DEFAULT_HIGH_ACCURACY_UPDATE_INTERVAL,
    DOMAIN,
    HIGH_ACCURACY_MODE_POLICY_ALWAYS,
    HIGH_ACCURACY_MODE_POLICY_CHARGING_ONLY,
)
from .coordinator import normalize_mac


def _entity_options(hass, domains: tuple[str, ...]) -> dict[str, str]:
    """Build multi-select options from loaded states."""
    return {
        state.entity_id: state.name or state.entity_id
        for state in sorted(
            (state for state in hass.states.async_all() if state.domain in domains),
            key=lambda state: state.entity_id,
        )
    }


def _tracker_label(state: State) -> str:
    """Create a readable label for a tracker option."""
    source_type = state.attributes.get("source_type")
    if source_type:
        return f"{state.name or state.entity_id} ({source_type})"
    return state.name or state.entity_id


def _iter_tracker_ids(value: Any) -> Iterable[str]:
    """Yield device tracker entity ids from person attributes."""
    if isinstance(value, str):
        if value.startswith("device_tracker."):
            yield value
        return

    if isinstance(value, (list, tuple, set)):
        for item in value:
            if isinstance(item, str) and item.startswith("device_tracker."):
                yield item


def _all_mobile_app_trackers(hass) -> list[State]:
    """Return all available mobile app device trackers."""
    registry = er.async_get(hass)
    trackers: list[State] = []
    for state in hass.states.async_all("device_tracker"):
        entry = registry.async_get(state.entity_id)
        if entry is not None and entry.platform == "mobile_app":
            trackers.append(state)

    return sorted(trackers, key=lambda state: state.entity_id)


def _person_tracker_candidates(hass, person_entity_id: str) -> list[State]:
    """Return likely phone trackers associated with a person."""
    person_state = hass.states.get(person_entity_id)
    if person_state is None:
        return []

    registry = er.async_get(hass)
    candidates: list[State] = []
    seen: set[str] = set()

    tracker_ids = [
        *list(_iter_tracker_ids(person_state.attributes.get("device_trackers"))),
    ]
    source = person_state.attributes.get("source")
    if isinstance(source, str) and source.startswith("device_tracker.") and source not in tracker_ids:
        tracker_ids.insert(0, source)

    for entity_id in tracker_ids:
        state = hass.states.get(entity_id)
        entry = registry.async_get(entity_id)
        if state is None or entry is None or entry.platform != "mobile_app":
            continue

        candidates.append(state)
        seen.add(entity_id)

    if candidates:
        return candidates

    return [state for state in _all_mobile_app_trackers(hass) if state.entity_id not in seen]


def _phone_schema(options: dict[str, str], default: str | None) -> vol.Schema:
    """Build the selection form for a single person."""
    if default is not None:
        return vol.Schema({vol.Optional("phone_tracker", default=default): vol.In(options)})

    return vol.Schema({vol.Required("phone_tracker"): vol.In(options)})


def _high_accuracy_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Build the high accuracy onboarding form."""
    data = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_ENABLE_HIGH_ACCURACY_MODE,
                default=data.get(
                    CONF_ENABLE_HIGH_ACCURACY_MODE, DEFAULT_ENABLE_HIGH_ACCURACY_MODE
                ),
            ): bool,
            vol.Required(
                CONF_HIGH_ACCURACY_MODE_POLICY,
                default=data.get(
                    CONF_HIGH_ACCURACY_MODE_POLICY, DEFAULT_HIGH_ACCURACY_MODE_POLICY
                ),
            ): vol.In(
                {
                    HIGH_ACCURACY_MODE_POLICY_ALWAYS: "Always while driving",
                    HIGH_ACCURACY_MODE_POLICY_CHARGING_ONLY: "Only while driving and charging",
                }
            ),
            vol.Required(
                CONF_HIGH_ACCURACY_UPDATE_INTERVAL,
                default=data.get(
                    CONF_HIGH_ACCURACY_UPDATE_INTERVAL,
                    DEFAULT_HIGH_ACCURACY_UPDATE_INTERVAL,
                ),
            ): vol.All(vol.Coerce(int), vol.Range(min=1)),
        }
    )


class RememberWhereIParkedConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Remember Where I Parked."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}
        self._remaining_people: list[str] = []
        self._selected_phone_trackers: dict[str, str] = {}

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
                self._remaining_people = list(selected_people)
                self._selected_phone_trackers = {}
                return await self.async_step_phones()

        return self.async_show_form(
            step_id="people",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PEOPLE): cv.multi_select(people_options),
                }
            ),
            errors=errors,
        )

    async def async_step_phones(self, user_input: dict[str, Any] | None = None):
        """Map each selected person to a companion-app phone."""
        errors: dict[str, str] = {}
        if not self._remaining_people:
            self._data[CONF_PHONE_TRACKERS] = self._selected_phone_trackers
            return await self.async_step_high_accuracy()

        person_entity_id = self._remaining_people[0]
        person_state = self.hass.states.get(person_entity_id)
        person_name = person_state.name if person_state is not None else person_entity_id
        candidates = _person_tracker_candidates(self.hass, person_entity_id)
        options = {state.entity_id: _tracker_label(state) for state in candidates}

        if not options:
            return self.async_show_form(
                step_id="phones",
                data_schema=vol.Schema({}),
                errors={"base": "no_mobile_app_trackers"},
                description_placeholders={"person_name": person_name},
            )

        default = candidates[0].entity_id if len(candidates) == 1 else None

        if user_input is not None:
            tracker = user_input.get("phone_tracker") or default
            if not tracker:
                errors["phone_tracker"] = "required"
            else:
                self._selected_phone_trackers[person_entity_id] = tracker
                self._remaining_people.pop(0)
                return await self.async_step_phones()

        return self.async_show_form(
            step_id="phones",
            data_schema=_phone_schema(options, default),
            errors=errors,
            description_placeholders={"person_name": person_name},
        )

    async def async_step_high_accuracy(self, user_input: dict[str, Any] | None = None):
        """Collect per-car high accuracy mode settings."""
        if user_input is not None:
            self._data.update(
                {
                    CONF_ENABLE_HIGH_ACCURACY_MODE: user_input[
                        CONF_ENABLE_HIGH_ACCURACY_MODE
                    ],
                    CONF_HIGH_ACCURACY_MODE_POLICY: user_input[
                        CONF_HIGH_ACCURACY_MODE_POLICY
                    ],
                    CONF_HIGH_ACCURACY_UPDATE_INTERVAL: user_input[
                        CONF_HIGH_ACCURACY_UPDATE_INTERVAL
                    ],
                }
            )
            return self.async_create_entry(
                title=self._data["name"],
                data=self._data,
            )

        return self.async_show_form(
            step_id="high_accuracy",
            data_schema=_high_accuracy_schema(self._data),
        )
