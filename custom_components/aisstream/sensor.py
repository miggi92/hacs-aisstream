"""Sensor platform for aisstream.io."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import DEGREE, UnitOfSpeed
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, NAVIGATIONAL_STATUS, SIGNAL_NEW_SHIP
from .coordinator import AISStreamClient, ShipData
from .entity import AISStreamShipEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class AISStreamSensorDescription(SensorEntityDescription):
    """Describes an aisstream.io sensor."""

    value_fn: Callable[[ShipData], object]


def _heading(ship: ShipData) -> int | None:
    # 511 means "not available" per the AIS spec.
    if ship.true_heading is None or ship.true_heading == 511:
        return None
    return ship.true_heading


SENSOR_DESCRIPTIONS: tuple[AISStreamSensorDescription, ...] = (
    AISStreamSensorDescription(
        key="speed",
        translation_key="speed_over_ground",
        native_unit_of_measurement=UnitOfSpeed.KNOTS,
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda ship: ship.sog,
    ),
    AISStreamSensorDescription(
        key="course",
        translation_key="course_over_ground",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda ship: ship.cog,
    ),
    AISStreamSensorDescription(
        key="heading",
        translation_key="true_heading",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_heading,
    ),
    AISStreamSensorDescription(
        key="navigational_status",
        translation_key="navigational_status",
        device_class=SensorDeviceClass.ENUM,
        options=list(NAVIGATIONAL_STATUS.values()),
        value_fn=lambda ship: (
            NAVIGATIONAL_STATUS.get(ship.navigational_status)
            if ship.navigational_status is not None
            else None
        ),
    ),
    AISStreamSensorDescription(
        key="destination",
        translation_key="destination",
        value_fn=lambda ship: ship.destination or None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up sensors for aisstream.io, added dynamically per vessel."""
    client: AISStreamClient = hass.data[DOMAIN][entry.entry_id]
    known_mmsi: set[str] = set()

    @callback
    def _add_ship(mmsi: str) -> None:
        if mmsi in known_mmsi:
            return
        known_mmsi.add(mmsi)
        async_add_entities(
            AISStreamSensor(client, mmsi, description)
            for description in SENSOR_DESCRIPTIONS
        )

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, f"{SIGNAL_NEW_SHIP}_{entry.entry_id}", _add_ship
        )
    )

    for mmsi in list(client.ships):
        _add_ship(mmsi)


class AISStreamSensor(AISStreamShipEntity, SensorEntity):
    """A single data point (speed, course, ...) of a tracked vessel."""

    entity_description: AISStreamSensorDescription

    def __init__(
        self,
        client: AISStreamClient,
        mmsi: str,
        description: AISStreamSensorDescription,
    ) -> None:
        super().__init__(client, mmsi)
        self.entity_description = description
        self._attr_unique_id = f"{mmsi}_{description.key}"

    @property
    def native_value(self):
        return self.entity_description.value_fn(self.ship)
