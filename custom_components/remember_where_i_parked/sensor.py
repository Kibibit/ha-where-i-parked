"""Sensors for Remember Where I Parked."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import KEY_ADDRESS, KEY_LATITUDE, KEY_LONGITUDE, KEY_STATUS
from .entity import RememberWhereIParkedEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up sensors from a config entry."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            RememberWhereIParkedStateSensor(coordinator),
            RememberWhereIParkedAddressSensor(coordinator),
            RememberWhereIParkedLatitudeSensor(coordinator),
            RememberWhereIParkedLongitudeSensor(coordinator),
        ]
    )


class RememberWhereIParkedStateSensor(RememberWhereIParkedEntity, SensorEntity):
    """Represent the current car state."""

    _attr_translation_key = "state"
    _attr_icon = "mdi:car-info"

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "state")

    @property
    def native_value(self) -> str | None:
        """Return the current driving state."""
        return self.coordinator.data.get(KEY_STATUS)


class RememberWhereIParkedAddressSensor(RememberWhereIParkedEntity, SensorEntity):
    """Represent the last known car address."""

    _attr_translation_key = "estimated_address"
    _attr_icon = "mdi:map-marker-radius"

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "estimated_address")

    @property
    def native_value(self) -> str | None:
        """Return the estimated address."""
        return self.coordinator.data.get(KEY_ADDRESS)


class RememberWhereIParkedLatitudeSensor(RememberWhereIParkedEntity, SensorEntity):
    """Represent the last known latitude."""

    _attr_translation_key = "latitude"
    _attr_icon = "mdi:latitude"
    _attr_suggested_display_precision = 6

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "latitude")

    @property
    def native_value(self) -> float | None:
        """Return the last known latitude."""
        return self.coordinator.data.get(KEY_LATITUDE)


class RememberWhereIParkedLongitudeSensor(RememberWhereIParkedEntity, SensorEntity):
    """Represent the last known longitude."""

    _attr_translation_key = "longitude"
    _attr_icon = "mdi:longitude"
    _attr_suggested_display_precision = 6

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "longitude")

    @property
    def native_value(self) -> float | None:
        """Return the last known longitude."""
        return self.coordinator.data.get(KEY_LONGITUDE)
