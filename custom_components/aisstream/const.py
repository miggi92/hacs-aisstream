"""Constants for the aisstream.io integration."""

DOMAIN = "aisstream"

AISSTREAM_WS_URL = "wss://stream.aisstream.io/v0/stream"

CONF_API_KEY = "api_key"
CONF_BOX_SOUTH = "box_south"
CONF_BOX_WEST = "box_west"
CONF_BOX_NORTH = "box_north"
CONF_BOX_EAST = "box_east"
CONF_MMSI_FILTER = "mmsi_filter"
CONF_ZONE = "zone_entity_id"
CONF_LOCATION = "location"

SUBENTRY_TYPE_AREA = "area"

DEFAULT_BOX_SOUTH = -90.0
DEFAULT_BOX_WEST = -180.0
DEFAULT_BOX_NORTH = 90.0
DEFAULT_BOX_EAST = 180.0

RECONNECT_DELAY_MIN = 5
RECONNECT_DELAY_MAX = 300
# A connection must stay up this long before the reconnect backoff resets.
STABLE_CONNECTION_SECONDS = 60

SIGNAL_NEW_SHIP = f"{DOMAIN}_new_ship"
SIGNAL_SHIP_UPDATE = f"{DOMAIN}_ship_update"
SIGNAL_SHIP_REMOVED = f"{DOMAIN}_ship_removed"

# How long a vessel is still considered "present" after its last position
# report, and how often the area count sensor re-evaluates presence.
PRESENCE_TIMEOUT_MINUTES = 20
PRESENCE_RECHECK_MINUTES = 2

# Vessel devices without a position report for this long are removed
# automatically (vessels on an area's MMSI list are kept), checked every
# STALE_VESSEL_SWEEP_MINUTES.
STALE_VESSEL_MINUTES = 60
STALE_VESSEL_SWEEP_MINUTES = 5

# AIS navigational status codes (ITU-R M.1371)
NAVIGATIONAL_STATUS = {
    0: "Under way using engine",
    1: "At anchor",
    2: "Not under command",
    3: "Restricted manoeuvrability",
    4: "Constrained by her draught",
    5: "Moored",
    6: "Aground",
    7: "Engaged in fishing",
    8: "Under way sailing",
    9: "Reserved (HSC)",
    10: "Reserved (WIG)",
    11: "Power-driven vessel towing astern",
    12: "Power-driven vessel pushing ahead",
    13: "Reserved",
    14: "AIS-SART / MOB / EPIRB",
    15: "Undefined",
}

# AIS "not available" sentinel values.
SOG_NOT_AVAILABLE = 102.3
COG_NOT_AVAILABLE = 360.0
HEADING_NOT_AVAILABLE = 511

# Vessels slower than this (knots) are drawn as a dot instead of an arrow.
STATIONARY_SOG_KNOTS = 0.5

# Vessel categories derived from the AIS ship type code, with the marker
# colour (loosely following the common MarineTraffic colour scheme) and icon.
SHIP_CATEGORY_UNKNOWN = "unknown"
SHIP_CATEGORIES: dict[str, tuple[str, str]] = {
    "cargo": ("#4caf50", "mdi:ferry"),
    "tanker": ("#e53935", "mdi:ferry"),
    "passenger": ("#1e88e5", "mdi:ferry"),
    "high_speed": ("#fdd835", "mdi:speedboat"),
    "fishing": ("#ff8a65", "mdi:fish"),
    "tug": ("#00acc1", "mdi:ship-wheel"),
    "special": ("#00acc1", "mdi:ship-wheel"),
    "sailing": ("#d500f9", "mdi:sail-boat"),
    "pleasure": ("#d500f9", "mdi:sail-boat"),
    "military": ("#546e7a", "mdi:ferry"),
    "other": ("#8d6e63", "mdi:ferry"),
    SHIP_CATEGORY_UNKNOWN: ("#9e9e9e", "mdi:ferry"),
}


def ship_category(ship_type: int | None) -> str:
    """Map an AIS ship type code (ITU-R M.1371) to a coarse category."""
    if not ship_type:
        return SHIP_CATEGORY_UNKNOWN
    if ship_type == 30:
        return "fishing"
    if ship_type in (31, 32, 52):
        return "tug"
    if ship_type in (33, 34, 50, 51, 53, 54, 55, 58, 59):
        return "special"
    if ship_type == 35:
        return "military"
    if ship_type == 36:
        return "sailing"
    if ship_type == 37:
        return "pleasure"
    if 40 <= ship_type <= 49:
        return "high_speed"
    if 60 <= ship_type <= 69:
        return "passenger"
    if 70 <= ship_type <= 79:
        return "cargo"
    if 80 <= ship_type <= 89:
        return "tanker"
    return "other"
