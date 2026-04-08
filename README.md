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
3. select one or more Bluetooth source entities and optional address source entities

## Notes about source entities

Companion app Bluetooth and geocoded address entities vary by platform and phone configuration. This first version intentionally lets you choose the entities manually so you can test against your own setup without hardcoding Android- or iOS-specific assumptions.

- Bluetooth source entities should contain the target MAC address somewhere in their state or attributes when the phone is connected to the car.
- Address source entities are optional. If none are configured, the integration falls back to a `"lat, lon"` string.
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
