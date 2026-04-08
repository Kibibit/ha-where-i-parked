"""Constants for Remember Where I Parked."""

from homeassistant.const import Platform

DOMAIN = "remember_where_i_parked"

PLATFORMS: tuple[Platform, ...] = (
    Platform.BINARY_SENSOR,
    Platform.DEVICE_TRACKER,
    Platform.SENSOR,
)

STORAGE_VERSION = 1
DEFAULT_SCAN_INTERVAL_SECONDS = 30

CONF_BLUETOOTH_MAC = "bluetooth_mac"
CONF_PEOPLE = "people"
CONF_PHONE_TRACKERS = "phone_trackers"

ATTR_DRIVER = "driver"
ATTR_ESTIMATED_ADDRESS = "estimated_address"
ATTR_MATCHED_BLUETOOTH_SENSOR = "matched_bluetooth_sensor"
ATTR_PARKED_AT = "parked_at"
ATTR_SOURCE_PERSON = "source_person"

KEY_DRIVING = "driving"
KEY_STATUS = "status"
KEY_LATITUDE = "latitude"
KEY_LONGITUDE = "longitude"
KEY_ADDRESS = "estimated_address"
KEY_DRIVER = "driver"
KEY_PARKED_AT = "parked_at"
KEY_SOURCE_PERSON = "source_person"
KEY_MATCHED_BLUETOOTH_SENSOR = "matched_bluetooth_sensor"

STATUS_DRIVING = "driving"
STATUS_PARKED = "parked"
