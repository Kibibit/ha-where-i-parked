# Remember Where I Parked

`Remember Where I Parked` is a Home Assistant custom integration inspired by this community idea: [Remember where I parked in home assistant](https://community.home-assistant.io/t/remember-where-i-parked-in-home-assistant/200698/54).

It is designed to be installed through HACS as a custom integration, not as a Home Assistant add-on.

## What it does

For each configured car, the integration creates a device with:

- a `device_tracker` entity for the car location
- a `binary_sensor` that is `on` when the car is considered driving
- sensors for state, estimated address, latitude, and longitude

The integration marks a car as driving when one of the configured Bluetooth source entities exposes the configured Bluetooth MAC address. When that Bluetooth connection disappears, it freezes the most recent known location as the parked location and persists that parked snapshot across Home Assistant restarts.

## Current onboarding flow

Each car is configured as its own integration entry:

1. enter a car name and the car Bluetooth MAC address
2. select the Home Assistant `person` entities that can drive that car
3. choose the companion-app phone for each selected person

## How phone selection works

The integration now derives source entities from the selected companion-app phone instead of asking you to pick raw sensors directly.

- If a selected person has only one likely mobile-app phone tracker, it is preselected automatically.
- Bluetooth connection is detected by scanning sensor and binary sensor entities attached to the selected phone device for the configured MAC address.
- Estimated address is derived from likely address or geocoded sensors attached to the selected phone device.
- If no address-like sensor is available, the integration falls back to a `"lat, lon"` string.
- If multiple configured people are moving at once, the integration currently uses the freshest selected `person` location as the car location while the Bluetooth MAC is connected.

## Install with HACS

1. Push this repository to GitHub.
2. In HACS, add it as a custom repository of type `Integration`.
3. Install `Remember Where I Parked`.
4. Restart Home Assistant.
5. Go to `Settings -> Devices & services -> Add integration`.
6. Add `Remember Where I Parked` once for each car you want to track.

## Good first tests

- Connect your phone to the car Bluetooth and confirm the car switches to driving.
- Drive a short distance and confirm the `device_tracker` follows the selected person location.
- Turn the car off or disconnect Bluetooth and confirm the parked location freezes.
- Restart Home Assistant and confirm the parked location is still present.
