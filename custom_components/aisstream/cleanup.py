"""Removal of vessel devices that stopped reporting."""
from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import AISStreamClient


def device_subentry_ids(device: dr.DeviceEntry, entry_id: str) -> set[str | None]:
    """Return the subentries of an entry a device belongs to."""
    if hasattr(device, "config_subentry_id"):
        # HA 2026.8+: a device belongs to exactly one entry and subentry.
        return {device.config_subentry_id}
    return set(device.config_entries_subentries.get(entry_id, set()))


def vessel_mmsi(device: dr.DeviceEntry, entry: ConfigEntry) -> str | None:
    """Return the MMSI of a vessel device, None for area devices."""
    for domain, identifier in device.identifiers:
        if domain == DOMAIN and identifier not in entry.subentries:
            return identifier
    return None


@callback
def async_remove_stale_vessels(
    hass: HomeAssistant,
    entry: ConfigEntry,
    client: AISStreamClient,
    max_age: timedelta,
    subentry_id: str | None = None,
    unseen_since: datetime | None = None,
) -> int:
    """Remove vessel devices without a position report within max_age.

    Vessels that haven't reported since setup (e.g. after a restart) count
    as last seen at ``unseen_since``, or as stale if that is None. Vessels
    on an area's MMSI list are always kept. Limited to one area if
    ``subentry_id`` is given. Returns the number of removed devices.
    """
    threshold = dt_util.utcnow() - max_age
    listed = {mmsi for area in client.areas.values() for mmsi in area.mmsi}
    device_registry = dr.async_get(hass)
    removed = 0

    for device in dr.async_entries_for_config_entry(
        device_registry, entry.entry_id
    ):
        mmsi = vessel_mmsi(device, entry)
        if mmsi is None or mmsi in listed:
            continue
        if subentry_id is not None and subentry_id not in device_subentry_ids(
            device, entry.entry_id
        ):
            continue
        ship = client.ships.get(mmsi)
        last_seen = (ship.last_position_update if ship else None) or unseen_since
        if last_seen is not None and last_seen >= threshold:
            continue
        client.forget_ship(mmsi)
        device_registry.async_remove_device(device.id)
        removed += 1

    return removed
