"""The aisstream.io integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .const import (
    CONF_API_KEY,
    CONF_MMSI,
    CONF_MMSI_FILTER,
    CONF_NAME,
    DOMAIN,
    SUBENTRY_TYPE_AREA,
    SUBENTRY_TYPE_VESSEL,
)
from .coordinator import AISStreamClient, AreaFilter, ShipData
from .geo import resolve_area_box

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.DEVICE_TRACKER,
    Platform.GEO_LOCATION,
    Platform.SENSOR,
]


def _collect_areas(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, AreaFilter]:
    """Resolve every area subentry into its bounding boxes and MMSI list."""
    areas: dict[str, AreaFilter] = {}

    for subentry_id, subentry in entry.subentries.items():
        if subentry.subentry_type != SUBENTRY_TYPE_AREA:
            continue
        boxes = resolve_area_box(hass, subentry.data)
        if boxes is None:
            raise ConfigEntryNotReady(
                f"Area '{subentry.title}' references a zone that isn't"
                " available yet"
            )
        areas[subentry_id] = AreaFilter(
            bounding_boxes=boxes,
            mmsi=frozenset(subentry.data.get(CONF_MMSI_FILTER) or []),
        )

    return areas


def _collect_vessels(entry: ConfigEntry) -> dict[str, ShipData]:
    """Return the individually tracked vessels, keyed by MMSI."""
    return {
        subentry.data[CONF_MMSI]: ShipData(
            mmsi=subentry.data[CONF_MMSI],
            name=subentry.data.get(CONF_NAME) or None,
            area_id=subentry_id,
        )
        for subentry_id, subentry in entry.subentries.items()
        if subentry.subentry_type == SUBENTRY_TYPE_VESSEL
    }


@callback
def _remove_orphaned_devices(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Drop devices not tied to any existing area or tracked vessel.

    Covers vessels created before they were assigned to areas, and anything
    left behind by an area removed while the entry wasn't loaded.
    """
    device_registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(
        device_registry, entry.entry_id
    ):
        if hasattr(device, "config_subentry_id"):
            # HA 2026.8+: a device belongs to exactly one entry and subentry.
            subentry_ids = {device.config_subentry_id}
        else:
            subentry_ids = device.config_entries_subentries.get(entry.entry_id, set())
        if any(subentry_id in entry.subentries for subentry_id in subentry_ids):
            continue
        device_registry.async_remove_device(device.id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up aisstream.io from a config entry."""
    areas = _collect_areas(hass, entry)
    _remove_orphaned_devices(hass, entry)

    client = AISStreamClient(
        hass=hass,
        entry_id=entry.entry_id,
        api_key=entry.data[CONF_API_KEY],
        areas=areas,
        vessels=_collect_vessels(entry),
    )
    client.start()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = client

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its data, options or subentries change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Allow deleting vessels seen in an area.

    Area devices and individually tracked vessels go with their subentry.
    """
    tracked_mmsi = _collect_vessels(entry)
    return not any(
        identifier in entry.subentries or identifier in tracked_mmsi
        for domain, identifier in device.identifiers
        if domain == DOMAIN
    )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        client: AISStreamClient = hass.data[DOMAIN].pop(entry.entry_id)
        await client.stop()
    return unload_ok
