"""Coordinator for Remember Where I Parked."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta
import logging
import re
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_FRIENDLY_NAME, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util, slugify

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
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DOMAIN,
    HIGH_ACCURACY_MODE_POLICY_ALWAYS,
    HIGH_ACCURACY_MODE_POLICY_CHARGING_ONLY,
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
CONNECTED_DEVICE_ATTRIBUTE_NAMES = (
    "connected_paired_devices",
    "connected_not_paired_devices",
)
CHARGING_BINARY_SENSOR_KEYWORDS = ("is_charging", "_charging", "plugged")
CHARGING_SENSOR_KEYWORDS = ("battery_state", "charger_type", "power_state", "charging")
CHARGING_ACTIVE_STATES = {
    "charging",
    "full",
    "plugged",
    "plugged_in",
    "ac",
    "usb",
    "wireless",
}
CHARGING_INACTIVE_STATES = {
    "not_charging",
    "not charging",
    "discharging",
    "unplugged",
    "none",
    "off",
}


@dataclass(slots=True)
class ActiveDriverDevice:
    """Configured driver device details used for high accuracy commands."""

    person_entity_id: str
    tracker_entity_id: str
    device_id: str
    notify_service: str | None
    charging_entity_id: str | None


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
        self._high_accuracy_lock = asyncio.Lock()
        self._high_accuracy_enabled = False
        self._high_accuracy_controlled_device: ActiveDriverDevice | None = None
        self._last_high_accuracy_reason: tuple[str | None, str | None] | None = None

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
        await self._async_disable_high_accuracy_mode()

    @callback
    def _watched_entities(self) -> set[str]:
        """Return entities that can change the computed car state."""
        return {
            *self.config_entry.data.get(CONF_PEOPLE, []),
            *self._phone_trackers(),
            *self._phone_sensor_entities(),
        }

    @callback
    def _handle_state_change(self, event: Event) -> None:
        """Refresh quickly when any relevant state changes."""
        updated_data = self._build_data()
        self.async_set_updated_data(updated_data)
        self.hass.async_create_task(self._async_sync_high_accuracy_mode(updated_data))

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
        data = self._build_data()
        await self._async_sync_high_accuracy_mode(data)
        return data

    async def _async_sync_high_accuracy_mode(self, data: dict[str, Any]) -> None:
        """Keep Android high accuracy mode aligned with the current driving state."""
        if not self.config_entry.data.get(
            CONF_ENABLE_HIGH_ACCURACY_MODE, DEFAULT_ENABLE_HIGH_ACCURACY_MODE
        ):
            await self._async_disable_high_accuracy_mode()
            self._last_high_accuracy_reason = None
            return

        async with self._high_accuracy_lock:
            if not data.get(KEY_DRIVING):
                await self._async_disable_high_accuracy_mode()
                self._last_high_accuracy_reason = None
                return

            active_device = self._resolve_active_configured_driver_device()
            should_enable, reason = self._evaluate_high_accuracy_mode_state(active_device)
            reason_key = (
                reason,
                active_device.tracker_entity_id if active_device is not None else None,
            )

            if reason_key != self._last_high_accuracy_reason:
                self._log_high_accuracy_skip_reason(reason, active_device)
                self._last_high_accuracy_reason = reason_key

            if self._high_accuracy_enabled and (
                active_device is None
                or self._high_accuracy_controlled_device is None
                or active_device.device_id != self._high_accuracy_controlled_device.device_id
            ):
                await self._async_disable_high_accuracy_mode()
                if self._high_accuracy_enabled:
                    return

            if should_enable and active_device is not None:
                await self._async_enable_high_accuracy_mode(active_device)
                return

            await self._async_disable_high_accuracy_mode()

    def _resolve_active_configured_driver_device(self) -> ActiveDriverDevice | None:
        """Resolve the active configured driver device for this car entry."""
        person_state = self._select_person_state()
        if person_state is None:
            return None

        tracker_entity_id = self.config_entry.data.get(CONF_PHONE_TRACKERS, {}).get(
            person_state.entity_id
        )
        if tracker_entity_id is None:
            return None

        registry = er.async_get(self.hass)
        tracker_entry = registry.async_get(tracker_entity_id)
        if tracker_entry is None or tracker_entry.device_id is None:
            return None

        return ActiveDriverDevice(
            person_entity_id=person_state.entity_id,
            tracker_entity_id=tracker_entity_id,
            device_id=tracker_entry.device_id,
            notify_service=self._mobile_app_notify_service(tracker_entity_id, tracker_entry.device_id),
            charging_entity_id=self._charging_state_entity(tracker_entry.device_id),
        )

    def _evaluate_high_accuracy_mode_state(
        self, active_device: ActiveDriverDevice | None
    ) -> tuple[bool, str | None]:
        """Return whether high accuracy mode should currently be enabled."""
        if active_device is None or active_device.notify_service is None:
            return (False, "no_controllable_active_device")

        if self._high_accuracy_mode_policy() == HIGH_ACCURACY_MODE_POLICY_ALWAYS:
            return (True, None)

        if active_device.charging_entity_id is None:
            return (False, "charging_state_unavailable")

        charging = self._charging_state(active_device.charging_entity_id)
        if charging is True:
            return (True, None)
        if charging is False:
            return (False, "not_charging")
        return (False, "charging_state_unavailable")

    async def _async_enable_high_accuracy_mode(self, active_device: ActiveDriverDevice) -> None:
        """Enable high accuracy mode for the active device if needed."""
        if (
            self._high_accuracy_enabled
            and self._high_accuracy_controlled_device is not None
            and self._high_accuracy_controlled_device.device_id == active_device.device_id
        ):
            return

        sent = await self._async_send_high_accuracy_mode_command(active_device, turn_on=True)
        if not sent:
            return

        self._high_accuracy_enabled = True
        self._high_accuracy_controlled_device = active_device
        _LOGGER.info(
            "Enabled High Accuracy Mode for car entry %s on device %s (%s) using policy %s",
            self.config_entry.entry_id,
            active_device.device_id,
            active_device.tracker_entity_id,
            self._high_accuracy_mode_policy(),
        )

    async def _async_disable_high_accuracy_mode(self) -> None:
        """Disable high accuracy mode for the currently controlled device if needed."""
        if not self._high_accuracy_enabled or self._high_accuracy_controlled_device is None:
            self._high_accuracy_controlled_device = None
            return

        active_device = self._high_accuracy_controlled_device
        sent = await self._async_send_high_accuracy_mode_command(active_device, turn_on=False)
        if not sent:
            return

        self._high_accuracy_enabled = False
        self._high_accuracy_controlled_device = None
        _LOGGER.info(
            "Disabled High Accuracy Mode for car entry %s on device %s (%s) using policy %s",
            self.config_entry.entry_id,
            active_device.device_id,
            active_device.tracker_entity_id,
            self._high_accuracy_mode_policy(),
        )

    async def _async_send_high_accuracy_mode_command(
        self, active_device: ActiveDriverDevice, *, turn_on: bool
    ) -> bool:
        """Send the Android companion command for high accuracy mode."""
        if active_device.notify_service is None:
            return False

        service_data: dict[str, Any] = {
            "message": "command_high_accuracy_mode",
            "data": {
                "command": "turn_on" if turn_on else "turn_off",
            },
        }
        if turn_on:
            service_data["data"]["high_accuracy_update_interval"] = (
                self.config_entry.data.get(
                    CONF_HIGH_ACCURACY_UPDATE_INTERVAL,
                    DEFAULT_HIGH_ACCURACY_UPDATE_INTERVAL,
                )
            )

        try:
            await self.hass.services.async_call(
                "notify",
                active_device.notify_service,
                service_data,
                blocking=True,
            )
        except Exception:  # noqa: BLE001
            _LOGGER.warning(
                "Failed to send High Accuracy Mode command for car entry %s to device %s (%s)",
                self.config_entry.entry_id,
                active_device.device_id,
                active_device.tracker_entity_id,
                exc_info=True,
            )
            return False

        return True

    def _mobile_app_notify_service(self, tracker_entity_id: str, device_id: str) -> str | None:
        """Resolve the notify.mobile_app service for a configured tracker device."""
        services = self.hass.services.async_services().get("notify", {})
        if not services:
            return None

        device_registry = dr.async_get(self.hass)
        device = device_registry.async_get(device_id)
        candidate_names = {
            f"mobile_app_{tracker_entity_id.split('.', 1)[1]}",
        }
        if device is not None:
            for name in (device.name_by_user, device.name):
                if name:
                    candidate_names.add(f"mobile_app_{slugify(name)}")

        for service_name in candidate_names:
            if service_name in services:
                return service_name

        return None

    def _charging_state_entity(self, device_id: str) -> str | None:
        """Resolve the best charging or power-state entity for a configured device."""
        registry = er.async_get(self.hass)
        binary_candidates: list[str] = []
        sensor_candidates: list[str] = []

        for entry in er.async_entries_for_device(registry, device_id):
            entity_id_lower = entry.entity_id.lower()
            state = self.hass.states.get(entry.entity_id)
            friendly_name = (
                str(state.attributes.get(ATTR_FRIENDLY_NAME, "")).lower()
                if state is not None
                else ""
            )

            if entry.domain == "binary_sensor" and any(
                keyword in entity_id_lower or keyword.replace("_", " ") in friendly_name
                for keyword in CHARGING_BINARY_SENSOR_KEYWORDS
            ):
                binary_candidates.append(entry.entity_id)
                continue

            if entry.domain == "sensor" and any(
                keyword in entity_id_lower or keyword.replace("_", " ") in friendly_name
                for keyword in CHARGING_SENSOR_KEYWORDS
            ):
                sensor_candidates.append(entry.entity_id)

        if binary_candidates:
            return sorted(binary_candidates)[0]
        if sensor_candidates:
            return sorted(sensor_candidates)[0]
        return None

    def _charging_state(self, entity_id: str) -> bool | None:
        """Return whether the selected charging entity confirms external power."""
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE, ""):
            return None

        normalized_state = str(state.state).strip().lower()
        if entity_id.startswith("binary_sensor."):
            if normalized_state == "on":
                return True
            if normalized_state == "off":
                return False

        if normalized_state in CHARGING_ACTIVE_STATES:
            return True
        if normalized_state in CHARGING_INACTIVE_STATES:
            return False
        return None

    def _high_accuracy_mode_policy(self) -> str:
        """Return the configured high accuracy mode policy."""
        return self.config_entry.data.get(
            CONF_HIGH_ACCURACY_MODE_POLICY,
            DEFAULT_HIGH_ACCURACY_MODE_POLICY,
        )

    def _log_high_accuracy_skip_reason(
        self, reason: str | None, active_device: ActiveDriverDevice | None
    ) -> None:
        """Log why high accuracy mode was not activated, when relevant."""
        if reason is None:
            return

        if reason == "no_controllable_active_device":
            _LOGGER.warning(
                "No controllable active mobile app device could be resolved for car entry %s from active device %s",
                self.config_entry.entry_id,
                active_device.device_id if active_device is not None else "unknown",
            )
            return

        if reason == "not_charging":
            _LOGGER.info(
                "High Accuracy Mode not enabled for car entry %s on device %s (%s) because policy %s requires charging",
                self.config_entry.entry_id,
                active_device.device_id if active_device is not None else "unknown",
                active_device.tracker_entity_id if active_device is not None else "unknown",
                self._high_accuracy_mode_policy(),
            )
            return

        if reason == "charging_state_unavailable":
            _LOGGER.warning(
                "High Accuracy Mode not enabled for car entry %s on device %s (%s) because charging state is unavailable for policy %s",
                self.config_entry.entry_id,
                active_device.device_id if active_device is not None else "unknown",
                active_device.tracker_entity_id if active_device is not None else "unknown",
                self._high_accuracy_mode_policy(),
            )

    def _find_connected_sensor(self) -> str | None:
        """Return the matching Bluetooth entity if the car is actively connected."""
        target_mac = self.config_entry.data[CONF_BLUETOOTH_MAC]
        for entity_id in self._bluetooth_connection_entities():
            state = self.hass.states.get(entity_id)
            if state is None:
                continue

            for text in self._connected_device_strings(state):
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
        for entity_id in self._address_sensor_entities():
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

    def _phone_trackers(self) -> list[str]:
        """Return configured phone tracker entity ids."""
        return list(self.config_entry.data.get(CONF_PHONE_TRACKERS, {}).values())

    def _phone_sensor_entities(self) -> list[str]:
        """Return sensor entities attached to configured phones."""
        return self._device_entities_for_domains(("sensor", "binary_sensor"))

    def _bluetooth_connection_entities(self) -> list[str]:
        """Return entities that specifically represent active Bluetooth connections."""
        entities: list[str] = []
        for entity_id in self._phone_sensor_entities():
            state = self.hass.states.get(entity_id)
            if state is None:
                continue

            entity_id_lower = entity_id.lower()
            friendly_name = str(state.attributes.get(ATTR_FRIENDLY_NAME, "")).lower()

            if "bluetooth_connection" in entity_id_lower:
                entities.append(entity_id)
                continue

            if "bluetooth connection" in friendly_name:
                entities.append(entity_id)
                continue

            if any(attribute_name in state.attributes for attribute_name in CONNECTED_DEVICE_ATTRIBUTE_NAMES):
                entities.append(entity_id)

        return entities

    def _address_sensor_entities(self) -> list[str]:
        """Return likely address sensors attached to configured phones."""
        keywords = ("geocoded", "address", "street", "location")
        entities = []
        for entity_id in self._device_entities_for_domains(("sensor",)):
            lowered = entity_id.lower()
            if any(keyword in lowered for keyword in keywords):
                entities.append(entity_id)
                continue

            state = self.hass.states.get(entity_id)
            if state is None:
                continue

            friendly_name = str(state.attributes.get(ATTR_FRIENDLY_NAME, "")).lower()
            if any(keyword in friendly_name for keyword in keywords):
                entities.append(entity_id)

        return entities

    def _device_entities_for_domains(self, domains: tuple[str, ...]) -> list[str]:
        """Return entities tied to the selected mobile app devices."""
        registry = er.async_get(self.hass)
        entity_ids: list[str] = []
        seen: set[str] = set()

        for tracker_entity_id in self._phone_trackers():
            tracker_entry = registry.async_get(tracker_entity_id)
            if tracker_entry is None or tracker_entry.device_id is None:
                continue

            for entry in er.async_entries_for_device(registry, tracker_entry.device_id):
                if entry.domain not in domains:
                    continue

                if entry.entity_id in seen:
                    continue

                entity_ids.append(entry.entity_id)
                seen.add(entry.entity_id)

        return entity_ids

    def _connected_device_strings(self, state) -> Iterable[str]:
        """Yield only active Bluetooth connection data from a state."""
        for attribute_name in CONNECTED_DEVICE_ATTRIBUTE_NAMES:
            yield from _iter_strings(state.attributes.get(attribute_name))
