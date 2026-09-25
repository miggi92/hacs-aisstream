"""Tests for vessel entities, area assignment and cleanup."""
from __future__ import annotations

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aisstream.const import DOMAIN, SUBENTRY_TYPE_AREA

SANTANDER = {"location": {"latitude": 43.46, "longitude": -3.79, "radius": 5000}}
MMSI_IN = "224612000"


def _entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="AISstream.io",
        data={"api_key": "test"},
        subentries_data=[
            ConfigSubentryData(
                data=SANTANDER,
                subentry_id="santander",
                subentry_type=SUBENTRY_TYPE_AREA,
                title="Santander",
                unique_id=None,
            )
        ],
    )
    entry.add_to_hass(hass)
    return entry


def _position(client, mmsi: str, lat: float, lon: float, name: str = "TEST SHIP"):
    client._handle_message(
        {
            "MessageType": "PositionReport",
            "MetaData": {
                "MMSI": int(mmsi),
                "ShipName": name,
                "latitude": lat,
                "longitude": lon,
            },
            "Message": {"PositionReport": {"Sog": 12.3, "Cog": 90.0}},
        }
    )


async def test_vessel_entities_devices_and_geo_location(hass: HomeAssistant) -> None:
    """A vessel in an area gets entities, a linked device and a map event."""
    entry = _entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    client = hass.data[DOMAIN][entry.entry_id]
    client.available = True

    _position(client, MMSI_IN, 43.46, -3.79)
    await hass.async_block_till_done()

    ent_reg = er.async_get(hass)
    tracker = ent_reg.async_get_entity_id("device_tracker", DOMAIN, f"{MMSI_IN}_position")
    assert tracker is not None
    assert ent_reg.async_get(tracker).config_subentry_id == "santander"

    dev_reg = dr.async_get(hass)
    ship_device = dev_reg.async_get(ent_reg.async_get(tracker).device_id)
    area_device = next(
        d
        for d in dr.async_entries_for_config_entry(dev_reg, entry.entry_id)
        if (DOMAIN, "santander") in d.identifiers
    )
    assert ship_device.via_device_id == area_device.id

    geo = [s for s in hass.states.async_all("geo_location")]
    assert len(geo) == 1
    assert geo[0].attributes["source"] == DOMAIN
    assert geo[0].attributes["area"] == "Santander"
    assert geo[0].name == "TEST SHIP"

    # Updates are written from the event loop without errors.
    _position(client, MMSI_IN, 43.47, -3.79)
    await hass.async_block_till_done()
    assert float(hass.states.get(tracker).attributes["latitude"]) == 43.47

    # Leaving the area removes the map event.
    _position(client, MMSI_IN, 45.0, -3.79)
    await hass.async_block_till_done()
    assert hass.states.async_all("geo_location") == []


async def test_vessel_outside_areas_is_ignored(hass: HomeAssistant) -> None:
    """Vessels outside every area don't create entities."""
    entry = _entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    client = hass.data[DOMAIN][entry.entry_id]

    _position(client, "111111111", 10.0, 10.0)
    await hass.async_block_till_done()

    assert hass.states.async_all("device_tracker") == []
    assert hass.states.async_all("geo_location") == []


async def test_removing_area_removes_its_vessels(hass: HomeAssistant) -> None:
    """Deleting an area subentry removes the vessel devices assigned to it."""
    entry = _entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    client = hass.data[DOMAIN][entry.entry_id]
    _position(client, MMSI_IN, 43.46, -3.79)
    await hass.async_block_till_done()

    dev_reg = dr.async_get(hass)
    assert any(
        (DOMAIN, MMSI_IN) in d.identifiers
        for d in dr.async_entries_for_config_entry(dev_reg, entry.entry_id)
    )

    assert hass.config_entries.async_remove_subentry(entry, "santander")
    await hass.async_block_till_done()

    assert dr.async_entries_for_config_entry(dev_reg, entry.entry_id) == []


async def test_orphaned_devices_removed_on_setup(hass: HomeAssistant) -> None:
    """Devices not tied to an existing area are cleaned up at setup."""
    entry = _entry(hass)
    dev_reg = dr.async_get(hass)
    dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, "999999999")}
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert not any(
        (DOMAIN, "999999999") in d.identifiers
        for d in dr.async_entries_for_config_entry(dev_reg, entry.entry_id)
    )
