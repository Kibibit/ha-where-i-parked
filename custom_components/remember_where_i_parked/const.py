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
DEFAULT_HIGH_ACCURACY_UPDATE_INTERVAL = 15
DEFAULT_ENABLE_HIGH_ACCURACY_MODE = True
DEFAULT_HIGH_ACCURACY_MODE_POLICY = "charging_only"
DEFAULT_MAX_PLAUSIBLE_SPEED_KMH = 220
DEFAULT_MAX_SINGLE_JUMP_KM = 50
MIN_TRUSTED_LOCATION_ELAPSED_SECONDS = 10

CONF_BLUETOOTH_MAC = "bluetooth_mac"
CONF_PEOPLE = "people"
CONF_PHONE_TRACKERS = "phone_trackers"
CONF_ENABLE_HIGH_ACCURACY_MODE = "enable_high_accuracy_mode"
CONF_HIGH_ACCURACY_UPDATE_INTERVAL = "high_accuracy_update_interval"
CONF_HIGH_ACCURACY_MODE_POLICY = "high_accuracy_mode_policy"

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

HIGH_ACCURACY_MODE_POLICY_ALWAYS = "always"
HIGH_ACCURACY_MODE_POLICY_CHARGING_ONLY = "charging_only"
