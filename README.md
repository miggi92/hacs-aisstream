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
- One Home Assistant **device per vessel**, created automatically the moment it's first seen inside one of your areas and **assigned to that area** (shown as connected via the area's device; a vessel keeps the area it was first seen in), with:
  - a `device_tracker` entity showing the vessel's live position on the map,
  - `sensor` entities for speed over ground, course over ground, true heading, navigational status, destination, ETA, ship type (cargo, tanker, passenger, fishing, ...) and draught,
  - further static data (IMO number, call sign, length/width) as attributes of the `device_tracker`.
- Both class A (commercial shipping) and class B (yachts, small fishing boats, ...) AIS transponders are supported.
- A short-lived **`geo_location` event per vessel currently inside one of your areas** (source `aisstream`, distance in km from the area's center). Events disappear automatically once a vessel leaves its area or hasn't reported a position for 20 minutes, so they are ideal for showing "ships around here right now" on a map (see below).
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

Each area can be edited or removed later from the integration's entry page. Removing an area also removes the vessel devices assigned to it. Individual vessel devices can be deleted from their device page; they are re-created if the vessel is seen again after the next restart or reload. To change the API key itself, remove and re-add the integration.

### A note on combining areas and MMSI filters

All areas you add share one aisstream.io subscription (one WebSocket connection, multiple bounding boxes). If you set MMSI filters on some areas, they currently apply across the whole subscription rather than being strictly scoped to that one area - for the common cases (either area-only tracking, or MMSI-only tracking with a single account) this makes no difference. It only matters if you mix a narrow area in one entry with an MMSI filter in another: a listed vessel could then show up as "in range" for a different area's box than the one its filter was added under.

## Showing vessels on a map

Add a map card and list `aisstream` as a geolocation source - every vessel currently inside one of your areas is shown, and ships that leave drop off the map on their own:

```yaml
type: map
geo_location_sources:
  - aisstream
```

Each vessel is drawn as an **arrow pointing in its heading**, coloured by ship type (green: cargo, red: tanker, blue: passenger, orange: fishing, turquoise: tug/special craft, magenta: sailing/pleasure craft, yellow: high-speed craft, grey: unknown). Vessels that aren't moving, or are at anchor/moored, are drawn as a dot. The same markers are used for the vessels' `device_tracker` entities, e.g.:

```yaml
type: map
entities:
  - device_tracker.aisstream_ever_given_position
```

If you prefer plain icons (a ferry, sail boat, anchor, ...) over the arrows, set `label_mode: icon` for an entity in the map card.

## Keeping vessels out of the logbook and database

Vessels come and go all the time, and every position report of a vessel updates its map event, so they can quickly flood the logbook and grow the recorder database. Home Assistant has no per-integration or per-device-class switch for this, but every vessel entity id created by this integration starts with `aisstream_` (e.g. `sensor.aisstream_ever_given_speed`, `geo_location.aisstream_ever_given_nearby`), so a single glob in `configuration.yaml` excludes all of them:

```yaml
logbook:
  exclude:
    entity_globs:
      - "*.aisstream_*"

# Optional: don't store vessel history in the database at all.
# This also removes them from the logbook and the history graphs.
recorder:
  exclude:
    entity_globs:
      - "*.aisstream_*"
```

The per-area "Vessels in area" sensors don't carry the prefix and stay recorded. Vessel entities created by an older version of this integration keep their old entity ids; remove those devices once (they are re-created with the new ids when the vessel is seen again) or rename them.

## About the data

- **Destination** is free text typed into the transponder by the ship's crew, not an id from aisstream.io. Most crews use the port's [UN/LOCODE](https://unece.org/trade/uncefact/unlocode) (e.g. `DEHAM` = Hamburg, `NLRTM` = Rotterdam, `ESSDR` = Santander), sometimes with a space (`DE HAM`) or as a route (`NLRTM>DEHAM`) - but anything goes, including typos and outdated entries.
- **ETA** is also entered by the crew and has no year; it is assumed to lie within half a year of now.
- Ship type, dimensions, draught, ETA and destination come from static-data messages, which vessels only broadcast every few minutes - these sensors can stay unknown for a while after a vessel first shows up.

## Notes

- Brand images (icon and logo, including dark variants) ship in `custom_components/aisstream/brand/` and are picked up automatically by Home Assistant 2026.3 or newer.
- Data is push-based (`iot_class: cloud_push`); entities update as soon as a new AIS message for that vessel arrives, there is no polling interval to configure.
- AIS "not available" values (`TrueHeading` 511, `Cog` 360, `Sog` 102.3) are reported as unknown.

## Development

Tests run against a real Home Assistant core via `pytest-homeassistant-custom-component` (Python 3.14):

```sh
pip install -r requirements_test.txt
pytest
```
