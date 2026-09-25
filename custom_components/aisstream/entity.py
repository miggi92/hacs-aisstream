"""Base entity for tracked aisstream.io vessels."""
from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, Entity

from .const import DOMAIN, SIGNAL_SHIP_UPDATE
from .coordinator import AISStreamClient, ShipData


class AISStreamShipEntity(Entity):
    """Base entity representing a single tracked vessel."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, client: AISStreamClient, mmsi: str) -> None:
        self._client = client
        self._mmsi = mmsi

    @property
    def ship(self) -> ShipData:
        """Return the latest known data for this vessel."""
        return self._client.ships[self._mmsi]

    @property
    def device_info(self) -> DeviceInfo:
        info = DeviceInfo(
            identifiers={(DOMAIN, self._mmsi)},
            name=self.ship.name or f"MMSI {self._mmsi}",
            manufacturer="aisstream.io",
            model="AIS vessel",
            configuration_url="https://aisstream.io/documentation",
        )
        if area_device_id := self._area_device_id():
            info["via_device_id"] = area_device_id
        return info

    def _area_device_id(self) -> str | None:
        """Return the registry id of the area device this vessel belongs to."""
        if self.ship.area_id is None:
            return None
        device_registry = dr.async_get(self.hass)
        identifier = (DOMAIN, self.ship.area_id)
        if hasattr(device_registry, "async_get_device_by_identifier"):
            device = device_registry.async_get_device_by_identifier(
                identifier, self._client.entry_id
            )
        else:
            device = device_registry.async_get_device(identifiers={identifier})
        return device.id if device else None

    @property
    def available(self) -> bool:
        return self._client.available and self._mmsi in self._client.ships

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_SHIP_UPDATE}_{self._mmsi}",
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()
