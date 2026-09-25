"""The aisstream.io integration."""
from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_time_interval

from .cleanup import async_remove_stale_vessels, device_subentry_ids, vessel_mmsi
from .const import (
    CONF_API_KEY,
    CONF_MMSI_FILTER,
    DOMAIN,
    STALE_VESSEL_MINUTES,
    STALE_VESSEL_SWEEP_MINUTES,
    SUBENTRY_TYPE_AREA,
)
from .coordinator import AISStreamClient, AreaFilter
from .geo import resolve_area_box

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
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


@callback
def _remove_orphaned_devices(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Drop devices not tied to any existing area.

    Covers vessels created before they were assigned to areas, and anything
    left behind by an area removed while the entry wasn't loaded.
    """
    device_registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(
        device_registry, entry.entry_id
    ):
        subentry_ids = device_subentry_ids(device, entry.entry_id)
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
    )
    if areas:
        client.start()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = client

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    @callback
    def _sweep(_now=None) -> None:
        async_remove_stale_vessels(
            hass,
            entry,
            client,
            timedelta(minutes=STALE_VESSEL_MINUTES),
            unseen_since=client.started_at,
        )

    entry.async_on_unload(
        async_track_time_interval(
            hass, _sweep, timedelta(minutes=STALE_VESSEL_SWEEP_MINUTES)
        )
    )
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its data, options or subentries change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Allow deleting vessel devices; area devices go with their area."""
    if any(
        identifier in entry.subentries
        for domain, identifier in device.identifiers
        if domain == DOMAIN
    ):
        return False
    # Forget the vessel so it is re-created as soon as it is seen again.
    client: AISStreamClient | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if client is not None and (mmsi := vessel_mmsi(device, entry)) is not None:
        client.forget_ship(mmsi)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        client: AISStreamClient = hass.data[DOMAIN].pop(entry.entry_id)
        await client.stop()
    return unload_ok
