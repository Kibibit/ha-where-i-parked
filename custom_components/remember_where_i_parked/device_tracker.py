"""Device tracker for Remember Where I Parked."""

from __future__ import annotations

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import KEY_LATITUDE, KEY_LONGITUDE
from .entity import RememberWhereIParkedEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the car location tracker."""
    coordinator = entry.runtime_data
    async_add_entities([RememberWhereIParkedTracker(coordinator)])


class RememberWhereIParkedTracker(RememberWhereIParkedEntity, TrackerEntity):
    """Represent the tracked car on the map."""

    _attr_translation_key = "location"
    _attr_icon = "mdi:car"
    _attr_source_type = SourceType.GPS

    def __init__(self, coordinator) -> None:
        """Initialize the tracker."""
        super().__init__(coordinator, "location")

    @property
    def latitude(self) -> float | None:
        """Return latitude value of the device."""
        return self.coordinator.data.get(KEY_LATITUDE)

    @property
    def longitude(self) -> float | None:
        """Return longitude value of the device."""
        return self.coordinator.data.get(KEY_LONGITUDE)

    @property
    def location_accuracy(self) -> int:
        """Return the assumed GPS accuracy."""
        return 25
