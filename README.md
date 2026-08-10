# hacs-aisstream

Home Assistant custom integration for [aisstream.io](https://aisstream.io) - live AIS ship-tracking data over a WebSocket feed.

## Features

- Connects to `wss://stream.aisstream.io/v0/stream` and keeps the connection alive (auto-reconnect with backoff).
- Track specific vessels by **MMSI number**, a **geographic bounding box**, or both at once.
- One Home Assistant **device per vessel**, created automatically the moment it's first seen, with:
  - a `device_tracker` entity showing the vessel's live position on the map,
  - `sensor` entities for speed over ground, course over ground, true heading, navigational status and destination.

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
3. Enter your API key, then either:
   - narrow the **bounding box** (south/west/north/east) to the sea area you care about, and/or
   - list the **MMSI numbers** of the vessels you want to track (comma-separated).

At least one of these filters must be set - subscribing to the entire planet without any filter would create a device for every AIS-transmitting vessel on earth (several thousand), which is rejected by the config flow on purpose.

Both the bounding box and the MMSI list can be changed later from the integration's *Configure* option.

## Notes

- Data is push-based (`iot_class: cloud_push`); entities update as soon as a new AIS message for that vessel arrives, there is no polling interval to configure.
- `TrueHeading` value `511` ("not available" per the AIS spec) is reported as unknown.
