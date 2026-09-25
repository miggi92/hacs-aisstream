"""Base entity for tracked aisstream.io vessels."""
from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, Entity
from homeassistant.util import slugify

from .const import DOMAIN, SHIP_CATEGORY_UNKNOWN, SIGNAL_SHIP_UPDATE, ship_category
from .coordinator import AISStreamClient, ShipData


def vessel_entity_id(domain: str, ship: ShipData, key: str) -> str:
    """Return the entity id for a new vessel entity.

    Every vessel entity id starts with ``aisstream_`` so all of them can be
    excluded from the logbook/recorder with a single ``*.aisstream_*`` glob.
    """
    return f"{domain}.aisstream_{slugify(ship.name or ship.mmsi)}_{key}"


class AISStreamShipEntity(Entity):
    """Base entity representing a single tracked vessel."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self, client: AISStreamClient, mmsi: str, domain: str, key: str
    ) -> None:
        self._client = client
        self._mmsi = mmsi
        self._attr_unique_id = f"{mmsi}_{key}"
        self.entity_id = vessel_entity_id(domain, self.ship, key)

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
            model=self._model(),
            serial_number=self._mmsi,
            configuration_url="https://aisstream.io/documentation",
        )
        if area_device_id := self._area_device_id():
            info["via_device_id"] = area_device_id
        return info

    def _model(self) -> str:
        category = ship_category(self.ship.ship_type)
        if category == SHIP_CATEGORY_UNKNOWN:
            return "AIS vessel"
        return f"AIS vessel ({category.replace('_', ' ')})"

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
        self._sync_device()
        self.async_write_ha_state()

    @callback
    def _sync_device(self) -> None:
        """Push name/type learnt from later static data to the device."""
        if (device := self.device_entry) is None:
            return
        changes = {}
        if (model := self._model()) != device.model:
            changes["model"] = model
        if self.ship.name and self.ship.name != device.name:
            changes["name"] = self.ship.name
        if changes:
            dr.async_get(self.hass).async_update_device(device.id, **changes)
