"""Entity base classes for Remember Where I Parked."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_DRIVER,
    ATTR_ESTIMATED_ADDRESS,
    ATTR_MATCHED_BLUETOOTH_SENSOR,
    ATTR_PARKED_AT,
    ATTR_SOURCE_PERSON,
    DOMAIN,
    KEY_ADDRESS,
    KEY_DRIVER,
    KEY_MATCHED_BLUETOOTH_SENSOR,
    KEY_PARKED_AT,
    KEY_SOURCE_PERSON,
)
from .coordinator import RememberWhereIParkedCoordinator


class RememberWhereIParkedEntity(CoordinatorEntity[RememberWhereIParkedCoordinator]):
    """Base entity for the integration."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: RememberWhereIParkedCoordinator, entity_suffix: str
    ) -> None:
        """Initialize the base entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{entity_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
            name=coordinator.config_entry.title,
            manufacturer="Custom",
            model="Tracked Car",
        )

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Return common attributes."""
        return {
            ATTR_DRIVER: self.coordinator.data.get(KEY_DRIVER),
            ATTR_ESTIMATED_ADDRESS: self.coordinator.data.get(KEY_ADDRESS),
            ATTR_MATCHED_BLUETOOTH_SENSOR: self.coordinator.data.get(
                KEY_MATCHED_BLUETOOTH_SENSOR
            ),
            ATTR_PARKED_AT: self.coordinator.data.get(KEY_PARKED_AT),
            ATTR_SOURCE_PERSON: self.coordinator.data.get(KEY_SOURCE_PERSON),
        }
