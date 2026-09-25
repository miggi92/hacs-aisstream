"""Tests for vessel entities, area assignment and cleanup."""
from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.aisstream.const import DOMAIN, SUBENTRY_TYPE_AREA

SANTANDER = {"location": {"latitude": 43.46, "longitude": -3.79, "radius": 5000}}
MMSI_IN = "224612000"


def _entry(hass: HomeAssistant, area_data: dict = SANTANDER) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="AISstream.io",
        data={"api_key": "test"},
        subentries_data=[
            ConfigSubentryData(
                data=area_data,
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


def _static(client, mmsi: str, **static):
    client._handle_message(
        {
            "MessageType": "ShipStaticData",
            "MetaData": {"MMSI": int(mmsi), "ShipName": "TEST SHIP"},
            "Message": {"ShipStaticData": static},
        }
    )


async def test_static_data_marker_and_entity_ids(hass: HomeAssistant) -> None:
    """Static data fills type/ETA/dimensions; entity ids share one prefix."""
    entry = _entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    client = hass.data[DOMAIN][entry.entry_id]
    client.available = True

    _position(client, MMSI_IN, 43.46, -3.79)
    _static(
        client,
        MMSI_IN,
        Type=71,
        ImoNumber=9811000,
        CallSign="ABCD ",
        Destination="ESSDR",
        MaximumStaticDraught=12.5,
        Dimension={"A": 200, "B": 50, "C": 20, "D": 20},
        Eta={"Month": 12, "Day": 24, "Hour": 18, "Minute": 30},
    )
    await hass.async_block_till_done()

    ent_reg = er.async_get(hass)
    vessel_ids = [
        e.entity_id
        for e in ent_reg.entities.values()
        if e.unique_id.startswith(MMSI_IN)
    ]
    assert vessel_ids
    assert all(".aisstream_test_ship_" in entity_id for entity_id in vessel_ids)
    assert hass.states.get("geo_location.aisstream_test_ship_nearby") is not None

    assert hass.states.get("sensor.aisstream_test_ship_ship_type").state == "cargo"
    assert hass.states.get("sensor.aisstream_test_ship_draught").state == "12.5"
    eta = hass.states.get("sensor.aisstream_test_ship_eta").state
    assert "-12-24T18:30:00" in eta

    tracker = hass.states.get("device_tracker.aisstream_test_ship_position")
    assert tracker.attributes["length_m"] == 250
    assert tracker.attributes["width_m"] == 40
    assert tracker.attributes["imo"] == 9811000
    assert tracker.attributes["call_sign"] == "ABCD"
    # Moving at 12.3 kn on course 90: a rotated green arrow.
    picture = tracker.attributes["entity_picture"]
    assert picture.startswith("data:image/svg+xml,")
    assert "rotate%2890" in picture and "4caf50" in picture

    dev_reg = dr.async_get(hass)
    device = next(
        d
        for d in dr.async_entries_for_config_entry(dev_reg, entry.entry_id)
        if (DOMAIN, MMSI_IN) in d.identifiers
    )
    assert device.model == "AIS vessel (cargo)"


async def test_class_b_vessels_are_tracked(hass: HomeAssistant) -> None:
    """Class B position reports create vessels; sentinels become unknown."""
    entry = _entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    client = hass.data[DOMAIN][entry.entry_id]
    client.available = True

    client._handle_message(
        {
            "MessageType": "StandardClassBPositionReport",
            "MetaData": {
                "MMSI": 211000001,
                "ShipName": "YACHT",
                "latitude": 43.46,
                "longitude": -3.79,
            },
            "Message": {
                "StandardClassBPositionReport": {
                    "Sog": 102.3,
                    "Cog": 360,
                    "TrueHeading": 511,
                }
            },
        }
    )
    client._handle_message(
        {
            "MessageType": "StaticDataReport",
            "MetaData": {"MMSI": 211000001, "ShipName": "YACHT"},
            "Message": {
                "StaticDataReport": {
                    "ReportB": {"Valid": True, "ShipType": 37, "CallSign": "DY1"}
                }
            },
        }
    )
    await hass.async_block_till_done()

    ship = client.ships["211000001"]
    assert ship.sog is None and ship.cog is None and ship.true_heading is None
    assert hass.states.get("sensor.aisstream_yacht_ship_type").state == "pleasure"
    assert hass.states.get("sensor.aisstream_yacht_speed").state == "unknown"
    tracker = hass.states.get("device_tracker.aisstream_yacht_position")
    assert tracker.attributes["icon"] == "mdi:sail-boat"
    # Not moving / no course: a dot instead of an arrow.
    assert "circle" in tracker.attributes["entity_picture"]


def _vessel_mmsis(hass: HomeAssistant, entry: MockConfigEntry) -> set[str]:
    return {
        identifier
        for device in dr.async_entries_for_config_entry(
            dr.async_get(hass), entry.entry_id
        )
        for domain, identifier in device.identifiers
        if domain == DOMAIN and identifier != "santander"
    }


async def test_remove_stale_vessels_button(hass: HomeAssistant) -> None:
    """The area button removes vessels that stopped reporting."""
    entry = _entry(hass)
    stale_mmsi = "224000001"
    unseen_mmsi = "224000002"
    dev_reg = dr.async_get(hass)
    # A vessel device left over from before a restart.
    dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        config_subentry_id="santander",
        identifiers={(DOMAIN, unseen_mmsi)},
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    client = hass.data[DOMAIN][entry.entry_id]
    client.available = True

    _position(client, MMSI_IN, 43.46, -3.79)
    _position(client, stale_mmsi, 43.46, -3.79, name="OLD SHIP")
    await hass.async_block_till_done()
    client.ships[stale_mmsi].last_position_update -= timedelta(minutes=30)
    assert _vessel_mmsis(hass, entry) == {MMSI_IN, stale_mmsi, unseen_mmsi}

    button = er.async_get(hass).async_get_entity_id(
        "button", DOMAIN, "santander_remove_stale_vessels"
    )
    assert button is not None
    await hass.services.async_call(
        "button", "press", {"entity_id": button}, blocking=True
    )
    await hass.async_block_till_done()

    assert _vessel_mmsis(hass, entry) == {MMSI_IN}
    assert hass.states.get("device_tracker.aisstream_old_ship_position") is None
    assert stale_mmsi not in client.ships

    # Seen again, the removed vessel gets its entities back right away.
    _position(client, stale_mmsi, 43.46, -3.79, name="OLD SHIP")
    await hass.async_block_till_done()
    assert stale_mmsi in _vessel_mmsis(hass, entry)
    assert hass.states.get("device_tracker.aisstream_old_ship_position") is not None


async def test_stale_vessels_expire_automatically(hass: HomeAssistant) -> None:
    """Vessels are removed after an hour without a position report."""
    entry = _entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    client = hass.data[DOMAIN][entry.entry_id]

    _position(client, MMSI_IN, 43.46, -3.79)
    await hass.async_block_till_done()

    # Recently seen: kept.
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=5))
    await hass.async_block_till_done()
    assert _vessel_mmsis(hass, entry) == {MMSI_IN}

    client.ships[MMSI_IN].last_position_update -= timedelta(minutes=61)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=10))
    await hass.async_block_till_done()
    assert _vessel_mmsis(hass, entry) == set()


async def test_listed_vessels_are_kept(hass: HomeAssistant) -> None:
    """Vessels on an area's MMSI list are never removed as stale."""
    entry = _entry(hass, {**SANTANDER, "mmsi_filter": [MMSI_IN]})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    client = hass.data[DOMAIN][entry.entry_id]

    _position(client, MMSI_IN, 43.46, -3.79)
    await hass.async_block_till_done()
    client.ships[MMSI_IN].last_position_update -= timedelta(days=1)

    button = er.async_get(hass).async_get_entity_id(
        "button", DOMAIN, "santander_remove_stale_vessels"
    )
    await hass.services.async_call(
        "button", "press", {"entity_id": button}, blocking=True
    )
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=10))
    await hass.async_block_till_done()
    assert _vessel_mmsis(hass, entry) == {MMSI_IN}
