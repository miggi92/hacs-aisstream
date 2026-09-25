# AISstream.io for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5?style=for-the-badge&logo=homeassistantcommunitystore&logoColor=white)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/miggi92/hacs-aisstream?style=for-the-badge)](https://github.com/miggi92/hacs-aisstream/releases)
![GitHub Downloads (all assets, all releases)](https://img.shields.io/github/downloads/miggi92/hacs-aisstream/total?style=for-the-badge)
[![GitHub License](https://img.shields.io/github/license/miggi92/hacs-aisstream?style=for-the-badge)](LICENSE)
![GitHub Repo stars](https://img.shields.io/github/stars/miggi92/hacs-aisstream?style=for-the-badge)

> Live AIS ship tracking in Home Assistant, powered by the free WebSocket feed of [aisstream.io](https://aisstream.io).

<img src="https://raw.githubusercontent.com/miggi92/hacs-aisstream/main/custom_components/aisstream/brand/icon.png" alt="AISstream.io logo" width="128">

Watch your harbor, a strait or your favorite ferry route: every vessel that shows up in one of your areas becomes a Home Assistant device with its live position, speed, course, destination and more - and appears on your map cards as an arrow pointing in its heading.

## Features

- **One API key, multiple monitored areas.** Enter your aisstream.io API key once, then add as many areas (harbors, straits, ...) as you like via *Add area* - all of them share a single WebSocket connection (auto-reconnect with backoff).
- **Track individual vessels anywhere** by their MMSI via *Track vessel* - e.g. your favorite ferry or a friend's sailing yacht - independent of your areas and wherever they are in the world.
- **Flexible areas**: pick a **location + radius on a map**, reuse an existing Home Assistant **zone**, or enter a manual bounding box. Optionally track specific vessels by **MMSI**.
- **One device per vessel**, created automatically the moment it's first seen inside one of your areas and **assigned to that area** (shown as connected via the area's device; a vessel keeps the area it was first seen in), with:
  - a `device_tracker` entity showing the vessel's live position on the map,
  - `sensor` entities for speed over ground, course over ground, true heading, navigational status, destination, ETA, ship type (cargo, tanker, passenger, fishing, ...) and draught,
  - further static data (IMO number, call sign, length/width) as attributes of the `device_tracker`.
- **Map-ready `geo_location` events** for every vessel currently inside one of your areas (source `aisstream`, distance in km from the area's center). They disappear automatically once a vessel leaves its area or hasn't reported a position for 20 minutes.
- **"Vessels in area" sensor** per area, counting the vessels that reported a position there within the last 20 minutes - handy for harbor-traffic dashboards and automations. Its attributes also expose live connection diagnostics (`connected`, `messages_received`, `last_message_at`, the resolved `bounding_box`).
- Class A (commercial shipping) and class B (yachts, small fishing boats, ...) AIS transponders are supported.
- Push-based (`cloud_push`): entities update as soon as a new AIS message arrives, no polling.
- UI in English and German.

## Requirements

- Home Assistant **2025.4** or newer (uses config subentries to manage multiple areas under one API key).
- A free [aisstream.io](https://aisstream.io) account and API key.

## Installation

### HACS (recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=miggi92&repository=hacs-aisstream&category=Integration)

1. Click the button above, or in HACS open the 3-dot menu -> *Custom repositories* and add `https://github.com/miggi92/hacs-aisstream` with category *Integration*.
2. Search for "AISstream.io" in HACS and download it.
3. Restart Home Assistant.

### Manual

1. Download `aisstream.zip` from the [latest release](https://github.com/miggi92/hacs-aisstream/releases/latest).
2. Extract it into `config/custom_components/aisstream/` of your Home Assistant installation.
3. Restart Home Assistant.

## Configuration

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=aisstream)

1. Create a free account at [aisstream.io](https://aisstream.io) and generate an API key.
2. In Home Assistant: *Settings -> Devices & Services -> Add Integration -> AISstream.io*, and enter your API key. This creates the "AISstream.io" hub entry - it won't track anything yet.
3. On the new entry's card, click **Add area** and set at least one of:
   - **Area**: click on the map and drop a pin on the harbor/area you want to monitor, then drag to set the radius - the easiest way to watch a specific port,
   - **Area (zone)**: pick an existing Home Assistant zone instead,
   - **Manual bounding box** (south/west/north/east), for advanced/non-circular areas,
   - and/or a comma-separated list of **MMSI numbers** of specific vessels to track.

   A picked location or zone takes precedence over the manual bounding box. At least one area or an MMSI list must be set - subscribing to the entire planet without any filter would create a device for every AIS-transmitting vessel on earth (several thousand), which is rejected on purpose.
4. Repeat *Add area* for every additional harbor/region - no need to re-enter the API key.

### Tracking individual vessels

To follow a specific vessel wherever it goes, click **Track vessel** on the entry's card and enter its **MMSI number** (9 digits - look it up e.g. on MarineTraffic or VesselFinder) and optionally a name. The vessel gets its device and entities right away - they stay unknown until it sends its first AIS message, and the AIS name replaces your name once it's received. Add one *Track vessel* entry per vessel.

Tracked vessels are followed world-wide, no area needed. They don't create map `geo_location` events (use their `device_tracker` on a map card instead), but still count towards a "Vessels in area" sensor while inside that area. Removing the *Track vessel* entry removes the vessel's device.

Because aisstream.io only allows one filter per connection (areas and MMSI numbers are combined with AND), tracked vessels use a **second WebSocket connection**, opened only if at least one vessel is tracked. aisstream.io may limit the number of simultaneous connections per account; if you see HTTP 429 warnings in the log, make sure no other client uses the same API key.

Each area can be edited or removed later from the integration's entry page. Removing an area also removes the vessel devices assigned to it. Individual vessel devices can be deleted from their device page; they are re-created if the vessel is seen again after the next restart or reload. To change the API key itself, remove and re-add the integration.

### Combining areas and MMSI filters

All areas share one aisstream.io subscription (one WebSocket connection, multiple bounding boxes). MMSI filters therefore apply across the whole subscription rather than being strictly scoped to the area they were added under. For the common cases (area-only tracking, or MMSI-only tracking) this makes no difference. It only matters if you mix a narrow area in one entry with an MMSI filter in another: a listed vessel could then show up as "in range" for a different area than the one its filter was added under. To follow specific vessels regardless of your areas, use *Track vessel* instead (see above), which has a subscription of its own.

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
- AIS "not available" values (`TrueHeading` 511, `Cog` 360, `Sog` 102.3) are reported as unknown.

## Troubleshooting

- **No vessels show up**: check the attributes of the area's "Vessels in area" sensor. `connected: false` points to a connection/API key problem; `connected: true` with `messages_received` staying at 0 usually means there is simply no AIS coverage (aisstream.io relies on volunteer receivers) or no traffic in that area right now.
- For more details, enable debug logging:

  ```yaml
  logger:
    logs:
      custom_components.aisstream: debug
  ```

Found a bug or have an idea? [Open an issue](https://github.com/miggi92/hacs-aisstream/issues).

## Development

Tests run against a real Home Assistant core via `pytest-homeassistant-custom-component` (Python 3.14):

```sh
pip install -r requirements_test.txt
pytest
```

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat: ...`, `fix: ...`, ...) - the [changelog](CHANGELOG.md) and release notes are generated from them.

### Releases

Releases are fully automated: closing a GitHub milestone named like a version (e.g. `0.7.0`) creates the tag and GitHub release, which then sets the version in `manifest.json`, attaches `aisstream.zip` for HACS, updates `CHANGELOG.md` and fills in the release notes. Don't bump the version or edit the changelog by hand.

## License

[MIT](LICENSE)
