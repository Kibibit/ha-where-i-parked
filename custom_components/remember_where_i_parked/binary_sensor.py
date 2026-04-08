"""Binary sensors for Remember Where I Parked."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import KEY_DRIVING
from .entity import RememberWhereIParkedEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up binary sensors from a config entry."""
    coordinator = entry.runtime_data
    async_add_entities([RememberWhereIParkedDrivingBinarySensor(coordinator)])


class RememberWhereIParkedDrivingBinarySensor(
    RememberWhereIParkedEntity, BinarySensorEntity
):
    """Represent whether the configured car is currently driving."""

    _attr_translation_key = "driving"
    _attr_icon = "mdi:car-connected"

    def __init__(self, coordinator) -> None:
        """Initialize the driving binary sensor."""
        super().__init__(coordinator, "driving")

    @property
    def is_on(self) -> bool:
        """Return True if the car is currently driving."""
        return bool(self.coordinator.data.get(KEY_DRIVING))
