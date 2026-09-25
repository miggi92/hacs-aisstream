"""Device tracker platform for aisstream.io."""
from __future__ import annotations

import logging

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_PICTURE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_NEW_SHIP, ship_category
from .coordinator import AISStreamClient
from .entity import AISStreamShipEntity
from .marker import ship_icon, ship_picture

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up device trackers for aisstream.io, added dynamically per vessel."""
    client: AISStreamClient = hass.data[DOMAIN][entry.entry_id]
    known_mmsi: set[str] = set()

    @callback
    def _add_ship(mmsi: str) -> None:
        area_id = client.ships[mmsi].area_id
        if mmsi in known_mmsi or area_id is None:
            return
        known_mmsi.add(mmsi)
        async_add_entities(
            [AISStreamDeviceTracker(client, mmsi)], config_subentry_id=area_id
        )

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, f"{SIGNAL_NEW_SHIP}_{entry.entry_id}", _add_ship
        )
    )

    for mmsi in list(client.ships):
        _add_ship(mmsi)


class AISStreamDeviceTracker(AISStreamShipEntity, TrackerEntity):
    """Represents the live position of a tracked vessel."""

    _attr_translation_key = "position"
    # The marker changes with every heading change; no need to store it.
    _unrecorded_attributes = frozenset({ATTR_ENTITY_PICTURE})

    def __init__(self, client: AISStreamClient, mmsi: str) -> None:
        super().__init__(client, mmsi, "device_tracker", "position")

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        return self.ship.latitude

    @property
    def longitude(self) -> float | None:
        return self.ship.longitude

    @property
    def icon(self) -> str:
        return ship_icon(self.ship)

    @property
    def entity_picture(self) -> str:
        return ship_picture(self.ship)

    @property
    def extra_state_attributes(self) -> dict:
        ship = self.ship
        return {
            "mmsi": ship.mmsi,
            "imo": ship.imo,
            "ship_name": ship.name,
            "call_sign": ship.call_sign,
            "ship_type": ship_category(ship.ship_type),
            "ship_type_code": ship.ship_type,
            "length_m": ship.length,
            "width_m": ship.width,
            "draught_m": ship.draught,
            "sog_knots": ship.sog,
            "cog_degrees": ship.cog,
            "true_heading": ship.true_heading,
            "destination": ship.destination,
            "eta": ship.eta.isoformat() if ship.eta else None,
            "last_position_update": ship.last_position_update.isoformat()
            if ship.last_position_update
            else None,
        }
