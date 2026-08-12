# hacs-aisstream

Home Assistant custom integration for [aisstream.io](https://aisstream.io) - live AIS ship-tracking data over a WebSocket feed.

## Features

- Connects to `wss://stream.aisstream.io/v0/stream` and keeps the connection alive (auto-reconnect with backoff).
- **One API key, multiple monitored areas.** Enter your aisstream.io API key once when adding the integration, then add as many areas (harbors, straits, ...) as you like afterward via *Add area* - all of them share a single WebSocket connection.
- Each area can be set up three ways:
  - pick a **location + radius directly on a map** (no extra setup needed),
  - reuse an existing Home Assistant **zone**,
  - or enter a manual bounding box (south/west/north/east).
  - Optionally add a comma-separated list of **MMSI numbers** to track specific vessels within (or regardless of) that area.
- One Home Assistant **device per vessel**, created automatically the moment it's first seen, with:
  - a `device_tracker` entity showing the vessel's live position on the map,
  - `sensor` entities for speed over ground, course over ground, true heading, navigational status and destination.
- A **"Vessels in area" sensor** per area, showing how many vessels have reported a position inside that specific area within the last 20 minutes - handy for harbor-traffic dashboards and automations. Its attributes also expose live connection diagnostics (`connected`, `messages_received`, `last_message_at`, the resolved `bounding_box`) to help tell a real connection problem apart from a quiet/uncovered area.

## Installation

### Via HACS (custom repository)

1. HACS -> Integrations -> the 3-dot menu -> *Custom repositories*.
2. Add this repository URL, category *Integration*.
3. Install "AISstream.io" and restart Home Assistant.

### Manual

Copy `custom_components/aisstream` into your Home Assistant `config/custom_components/` folder and restart.

Requires Home Assistant 2025.4 or newer (uses the config subentries feature to manage multiple areas under one API key).

## Configuration

1. Create a free account at [aisstream.io](https://aisstream.io) and generate an API key.
2. In Home Assistant: *Settings -> Devices & Services -> Add Integration -> AISstream.io*, and enter your API key. This creates the "AISstream.io" hub entry - it won't track anything yet.
3. On the new entry's card, click **Add area** and set at least one of:
   - **Area**: click on the map and drop a pin on the harbor/area you want to monitor, then drag to set the radius - this is the easiest way to watch a specific port,
   - **Area (zone)**: pick an existing Home Assistant zone instead, if you already have one for the location,
   - **Manual bounding box** (south/west/north/east), for advanced/non-circular areas,
   - and/or a comma-separated list of **MMSI numbers** of specific vessels to track.

   If a picked location or a zone is set, it takes precedence over the manual bounding box. At least one area or an MMSI list must be set - subscribing to the entire planet without any filter would create a device for every AIS-transmitting vessel on earth (several thousand), which is rejected on purpose.
4. Repeat *Add area* for every additional harbor/region you want to monitor - no need to re-enter the API key.

Each area can be edited or removed later from the integration's entry page. To change the API key itself, remove and re-add the integration.

### A note on combining areas and MMSI filters

All areas you add share one aisstream.io subscription (one WebSocket connection, multiple bounding boxes). If you set MMSI filters on some areas, they currently apply across the whole subscription rather than being strictly scoped to that one area - for the common cases (either area-only tracking, or MMSI-only tracking with a single account) this makes no difference. It only matters if you mix a narrow area in one entry with an MMSI filter in another: a listed vessel could then show up as "in range" for a different area's box than the one its filter was added under.

## Notes

- Data is push-based (`iot_class: cloud_push`); entities update as soon as a new AIS message for that vessel arrives, there is no polling interval to configure.
- `TrueHeading` value `511` ("not available" per the AIS spec) is reported as unknown.
