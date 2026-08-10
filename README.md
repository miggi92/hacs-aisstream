# hacs-aisstream

Home Assistant custom integration for [aisstream.io](https://aisstream.io) - live AIS ship-tracking data over a WebSocket feed.

## Features

- Connects to `wss://stream.aisstream.io/v0/stream` and keeps the connection alive (auto-reconnect with backoff).
- Track specific vessels by **MMSI number**, an **area** (e.g. a harbor), or both at once. The area can be set three ways:
  - pick a **location + radius directly on a map** in the config flow (no extra setup needed),
  - reuse an existing Home Assistant **zone**,
  - or enter a manual bounding box (south/west/north/east).
- One Home Assistant **device per vessel**, created automatically the moment it's first seen, with:
  - a `device_tracker` entity showing the vessel's live position on the map,
  - `sensor` entities for speed over ground, course over ground, true heading, navigational status and destination.
- A **"Vessels in area" sensor** per integration entry, showing how many vessels have reported a position in the monitored area within the last 20 minutes - handy for harbor-traffic dashboards and automations.

## Installation

### Via HACS (custom repository)

1. HACS -> Integrations -> the 3-dot menu -> *Custom repositories*.
2. Add this repository URL, category *Integration*.
3. Install "AISstream.io" and restart Home Assistant.

### Manual

Copy `custom_components/aisstream` into your Home Assistant `config/custom_components/` folder and restart.

## Configuration

1. Create a free account at [aisstream.io](https://aisstream.io) and generate an API key.
2. In Home Assistant: *Settings -> Devices & Services -> Add Integration -> AISstream.io*.
3. Enter your API key, then set at least one of:
   - **Area**: click on the map and drop a pin on the harbor/area you want to monitor, then drag to set the radius - this is the easiest way to watch a specific port,
   - **Area (zone)**: pick an existing Home Assistant zone instead, if you already have one for the location,
   - **Manual bounding box** (south/west/north/east), for advanced/non-circular areas,
   - and/or a comma-separated list of **MMSI numbers** of specific vessels to track.

If a picked location or a zone is set, it takes precedence over the manual bounding box. At least one area or an MMSI list must be set - subscribing to the entire planet without any filter would create a device for every AIS-transmitting vessel on earth (several thousand), which is rejected by the config flow on purpose.

The area and the MMSI list can both be changed later from the integration's *Configure* option.

## Notes

- Data is push-based (`iot_class: cloud_push`); entities update as soon as a new AIS message for that vessel arrives, there is no polling interval to configure.
- `TrueHeading` value `511` ("not available" per the AIS spec) is reported as unknown.
