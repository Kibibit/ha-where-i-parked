"""Coordinator for Remember Where I Parked."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import timedelta
import logging
import re
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_FRIENDLY_NAME, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ADDRESS_SENSORS,
    CONF_BLUETOOTH_MAC,
    CONF_BLUETOOTH_SENSORS,
    CONF_PEOPLE,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DOMAIN,
    KEY_ADDRESS,
    KEY_DRIVER,
    KEY_DRIVING,
    KEY_LATITUDE,
    KEY_LONGITUDE,
    KEY_MATCHED_BLUETOOTH_SENSOR,
    KEY_PARKED_AT,
    KEY_SOURCE_PERSON,
    KEY_STATUS,
    STATUS_DRIVING,
    STATUS_PARKED,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)

MAC_ADDRESS_PATTERN = re.compile(
    r"(?i)(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}|[0-9a-f]{12}"
)


def normalize_mac(value: str | None) -> str | None:
    """Normalize a Bluetooth MAC address to uppercase colon-separated form."""
    if not value:
        return None

    compact = re.sub(r"[^0-9A-Fa-f]", "", value)
    if len(compact) != 12:
        return None

    compact = compact.upper()
    return ":".join(compact[index : index + 2] for index in range(0, 12, 2))


def _iter_strings(value: Any) -> Iterable[str]:
    """Yield strings found in a nested structure."""
    if value is None:
        return

    if isinstance(value, str):
        yield value
        return

    if isinstance(value, dict):
        for key, nested_value in value.items():
            yield str(key)
            yield from _iter_strings(nested_value)
        return

    if isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _iter_strings(item)
        return


class RememberWhereIParkedCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Keep car state in sync from Home Assistant entities."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL_SECONDS),
        )
        self.config_entry = entry
        self._store = Store[dict[str, Any]](hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}")
        self._parked_snapshot: dict[str, Any] = {}
        self._remove_listener = None

    async def async_initialize(self) -> None:
        """Load persisted parked state and start listening for updates."""
        self._parked_snapshot = await self._store.async_load() or {}
        watched_entities = list(self._watched_entities())
        if watched_entities:
            self._remove_listener = async_track_state_change_event(
                self.hass, watched_entities, self._handle_state_change
            )
        await self.async_config_entry_first_refresh()

    async def async_shutdown(self) -> None:
        """Clean up listeners."""
        if self._remove_listener is not None:
            self._remove_listener()
            self._remove_listener = None

    @callback
    def _watched_entities(self) -> set[str]:
        """Return entities that can change the computed car state."""
        return {
            *self.config_entry.data.get(CONF_PEOPLE, []),
            *self.config_entry.data.get(CONF_BLUETOOTH_SENSORS, []),
            *self.config_entry.data.get(CONF_ADDRESS_SENSORS, []),
        }

    @callback
    def _handle_state_change(self, event: Event) -> None:
        """Refresh quickly when any relevant state changes."""
        self.async_set_updated_data(self._build_data())

    def _build_data(self) -> dict[str, Any]:
        """Build current car state from configured entities."""
        matched_sensor = self._find_connected_sensor()
        connected = matched_sensor is not None
        person_state = self._select_person_state()

        latitude, longitude = self._coordinates_from_state(person_state)
        estimated_address = self._select_address(latitude, longitude)
        driver = self._friendly_name(person_state)
        source_person = person_state.entity_id if person_state is not None else None

        if connected:
            live_data = {
                KEY_DRIVING: True,
                KEY_STATUS: STATUS_DRIVING,
                KEY_LATITUDE: latitude if latitude is not None else self._current_value(KEY_LATITUDE),
                KEY_LONGITUDE: longitude if longitude is not None else self._current_value(KEY_LONGITUDE),
                KEY_ADDRESS: estimated_address
                or self._current_value(KEY_ADDRESS)
                or self._coordinate_string(latitude, longitude),
                KEY_DRIVER: driver or self._current_value(KEY_DRIVER),
                KEY_PARKED_AT: self._parked_snapshot.get(KEY_PARKED_AT),
                KEY_SOURCE_PERSON: source_person or self._current_value(KEY_SOURCE_PERSON),
                KEY_MATCHED_BLUETOOTH_SENSOR: matched_sensor,
            }
            return live_data

        if self.data and self.data.get(KEY_DRIVING):
            parked_data = {
                KEY_DRIVING: False,
                KEY_STATUS: STATUS_PARKED,
                KEY_LATITUDE: self.data.get(KEY_LATITUDE),
                KEY_LONGITUDE: self.data.get(KEY_LONGITUDE),
                KEY_ADDRESS: self.data.get(KEY_ADDRESS),
                KEY_DRIVER: self.data.get(KEY_DRIVER),
                KEY_PARKED_AT: dt_util.utcnow().isoformat(),
                KEY_SOURCE_PERSON: self.data.get(KEY_SOURCE_PERSON),
                KEY_MATCHED_BLUETOOTH_SENSOR: self.data.get(KEY_MATCHED_BLUETOOTH_SENSOR),
            }
            self._parked_snapshot = parked_data
            self.hass.async_create_task(self._store.async_save(parked_data))
            return parked_data

        if self._parked_snapshot:
            return {
                **self._parked_snapshot,
                KEY_DRIVING: False,
                KEY_STATUS: STATUS_PARKED,
            }

        return {
            KEY_DRIVING: False,
            KEY_STATUS: STATUS_PARKED,
            KEY_LATITUDE: latitude,
            KEY_LONGITUDE: longitude,
            KEY_ADDRESS: estimated_address or self._coordinate_string(latitude, longitude),
            KEY_DRIVER: driver,
            KEY_PARKED_AT: None,
            KEY_SOURCE_PERSON: source_person,
            KEY_MATCHED_BLUETOOTH_SENSOR: None,
        }

    async def _async_update_data(self) -> dict[str, Any]:
        """Update the tracked car state."""
        return self._build_data()

    def _find_connected_sensor(self) -> str | None:
        """Return the matching Bluetooth entity if the car is connected."""
        target_mac = self.config_entry.data[CONF_BLUETOOTH_MAC]
        for entity_id in self.config_entry.data.get(CONF_BLUETOOTH_SENSORS, []):
            state = self.hass.states.get(entity_id)
            if state is None:
                continue

            for text in _iter_strings({"state": state.state, "attributes": state.attributes}):
                for match in MAC_ADDRESS_PATTERN.finditer(text):
                    if normalize_mac(match.group(0)) == target_mac:
                        return entity_id

        return None

    def _select_person_state(self):
        """Select the freshest configured person that has coordinates."""
        candidates = []
        for entity_id in self.config_entry.data.get(CONF_PEOPLE, []):
            state = self.hass.states.get(entity_id)
            if state is None:
                continue

            latitude, longitude = self._coordinates_from_state(state)
            if latitude is None or longitude is None:
                continue

            candidates.append(state)

        if not candidates:
            return None

        return max(candidates, key=lambda state: state.last_updated)

    def _coordinates_from_state(self, state) -> tuple[float | None, float | None]:
        """Extract numeric coordinates from a state."""
        if state is None:
            return (None, None)

        latitude = state.attributes.get("latitude")
        longitude = state.attributes.get("longitude")

        if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
            return (None, None)

        return (float(latitude), float(longitude))

    def _select_address(
        self, latitude: float | None, longitude: float | None
    ) -> str | None:
        """Pick a human-readable address from configured sensors."""
        freshest = None
        for entity_id in self.config_entry.data.get(CONF_ADDRESS_SENSORS, []):
            state = self.hass.states.get(entity_id)
            if state is None or state.state in ("", STATE_UNKNOWN, STATE_UNAVAILABLE):
                continue

            if freshest is None or state.last_updated > freshest.last_updated:
                freshest = state

        if freshest is not None:
            return str(freshest.state)

        return self._coordinate_string(latitude, longitude)

    def _current_value(self, key: str) -> Any:
        """Return the best known current value for a key."""
        if self.data and self.data.get(key) is not None:
            return self.data.get(key)
        return self._parked_snapshot.get(key)

    def _friendly_name(self, state) -> str | None:
        """Return a friendly name for the selected person."""
        if state is None:
            return None
        return state.attributes.get(ATTR_FRIENDLY_NAME) or state.name

    def _coordinate_string(
        self, latitude: float | None, longitude: float | None
    ) -> str | None:
        """Fallback human-readable location."""
        if latitude is None or longitude is None:
            return None
        return f"{latitude:.6f}, {longitude:.6f}"
