"""Geolocation platform for aisstream.io.

Creates a short-lived geolocation event for every vessel currently present
in one of the monitored areas, so the map card can show them with
``geo_location_sources: [aisstream]``. Events disappear again once a vessel
leaves its area or stops reporting.
"""
from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.components.geo_location import GeolocationEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_PICTURE, UnitOfLength
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util
from homeassistant.util.location import distance

from .const import (
    DOMAIN,
    PRESENCE_TIMEOUT_MINUTES,
    SIGNAL_NEW_SHIP,
    SIGNAL_SHIP_UPDATE,
    ship_category,
)
from .coordinator import AISStreamClient, ShipData
from .entity import vessel_entity_id
from .geo import point_in_box
from .marker import ship_icon, ship_picture

_LOGGER = logging.getLogger(__name__)

SWEEP_INTERVAL = timedelta(minutes=1)


def _is_present(client: AISStreamClient, ship: ShipData) -> bool:
    """Return whether a vessel recently reported a position inside its area."""
    area = client.areas.get(ship.area_id) if ship.area_id else None
    if (
        area is None
        or ship.latitude is None
        or ship.longitude is None
        or ship.last_position_update is None
    ):
        return False
    threshold = dt_util.utcnow() - timedelta(minutes=PRESENCE_TIMEOUT_MINUTES)
    if ship.last_position_update < threshold:
        return False
    return any(
        point_in_box(ship.latitude, ship.longitude, [box])
        for box in area.bounding_boxes
    )


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Keep one geolocation event per vessel present in a monitored area."""
    client: AISStreamClient = hass.data[DOMAIN][entry.entry_id]
    events: dict[str, AISStreamGeolocationEvent] = {}

    @callback
    def _removed(event: AISStreamGeolocationEvent) -> None:
        if events.get(event.mmsi) is event:
            del events[event.mmsi]

    @callback
    def _sync(*_args) -> None:
        new_events = []
        taken = {event.entity_id for event in events.values()}
        for mmsi, ship in list(client.ships.items()):
            present = _is_present(client, ship)
            if present and mmsi not in events:
                event = AISStreamGeolocationEvent(client, entry, mmsi, _removed)
                # Events aren't in the entity registry, so a vessel sharing
                # its name with another one falls back to an MMSI-based id.
                if event.entity_id in taken or hass.states.get(event.entity_id):
                    event.entity_id = f"geo_location.aisstream_{mmsi}_nearby"
                taken.add(event.entity_id)
                events[mmsi] = event
                new_events.append(event)
            elif not present and mmsi in events:
                events[mmsi].async_remove_event()
        if new_events:
            async_add_entities(new_events)

    entry.async_on_unload(
        async_dispatcher_connect(hass, f"{SIGNAL_NEW_SHIP}_{entry.entry_id}", _sync)
    )
    entry.async_on_unload(async_track_time_interval(hass, _sync, SWEEP_INTERVAL))
    _sync()


class AISStreamGeolocationEvent(GeolocationEvent):
    """A vessel currently inside one of the monitored areas."""

    _attr_should_poll = False
    _attr_source = DOMAIN
    _attr_unit_of_measurement = UnitOfLength.KILOMETERS
    _unrecorded_attributes = frozenset({ATTR_ENTITY_PICTURE})

    def __init__(
        self,
        client: AISStreamClient,
        entry: ConfigEntry,
        mmsi: str,
        on_remove,
    ) -> None:
        self._client = client
        self._entry = entry
        self._mmsi = mmsi
        self._removed_callback = on_remove
        self._removing = False
        self.entity_id = vessel_entity_id("geo_location", self.ship, "nearby")

    @property
    def mmsi(self) -> str:
        return self._mmsi

    @property
    def ship(self) -> ShipData:
        return self._client.ships[self._mmsi]

    @property
    def name(self) -> str:
        return self.ship.name or f"MMSI {self._mmsi}"

    @property
    def icon(self) -> str:
        return ship_icon(self.ship)

    @property
    def entity_picture(self) -> str:
        return ship_picture(self.ship)

    @property
    def latitude(self) -> float | None:
        return self.ship.latitude

    @property
    def longitude(self) -> float | None:
        return self.ship.longitude

    @property
    def distance(self) -> float | None:
        """Distance in km from the center of the vessel's area."""
        ship = self.ship
        area = self._client.areas.get(ship.area_id) if ship.area_id else None
        if area is None or ship.latitude is None or ship.longitude is None:
            return None
        (south, west), (north, east) = area.bounding_boxes[0]
        meters = distance(
            ship.latitude, ship.longitude, (south + north) / 2, (west + east) / 2
        )
        return round(meters / 1000, 2) if meters is not None else None

    @property
    def extra_state_attributes(self) -> dict:
        ship = self.ship
        subentry = self._entry.subentries.get(ship.area_id) if ship.area_id else None
        return {
            "mmsi": ship.mmsi,
            "area": subentry.title if subentry else None,
            "ship_type": ship_category(ship.ship_type),
            "sog_knots": ship.sog,
            "cog_degrees": ship.cog,
            "true_heading": ship.true_heading,
            "destination": ship.destination,
            "last_position_update": ship.last_position_update.isoformat()
            if ship.last_position_update
            else None,
        }

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_SHIP_UPDATE}_{self._mmsi}",
                self._handle_update,
            )
        )

    async def async_will_remove_from_hass(self) -> None:
        self._removed_callback(self)

    @callback
    def _handle_update(self) -> None:
        if not _is_present(self._client, self.ship):
            self.async_remove_event()
            return
        self.async_write_ha_state()

    @callback
    def async_remove_event(self) -> None:
        """Remove this event once the vessel has left its area."""
        if self._removing:
            return
        self._removing = True
        self.hass.async_create_task(self.async_remove(force_remove=True))
