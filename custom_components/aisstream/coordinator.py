"""WebSocket client that maintains the connection to aisstream.io."""
from __future__ import annotations

import asyncio
import contextlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import logging

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

from .const import (
    AISSTREAM_WS_URL,
    COG_NOT_AVAILABLE,
    HEADING_NOT_AVAILABLE,
    RECONNECT_DELAY_MAX,
    RECONNECT_DELAY_MIN,
    SIGNAL_NEW_SHIP,
    SIGNAL_SHIP_REMOVED,
    SIGNAL_SHIP_UPDATE,
    SOG_NOT_AVAILABLE,
    STABLE_CONNECTION_SECONDS,
)
from .geo import point_in_box

_LOGGER = logging.getLogger(__name__)

POSITION_MESSAGE_TYPES = (
    "PositionReport",
    "StandardClassBPositionReport",
    "ExtendedClassBPositionReport",
)


def _available(value, not_available):
    """Return value unless it is the AIS "not available" sentinel."""
    if value is None or value >= not_available:
        return None
    return value


def _parse_eta(eta: dict | None, now: datetime) -> datetime | None:
    """Turn an AIS ETA (month/day/hour/minute, no year, UTC) into a datetime.

    The year is picked so the ETA lands within half a year of now.
    """
    if not eta:
        return None
    month, day = eta.get("Month") or 0, eta.get("Day") or 0
    hour, minute = eta.get("Hour", 24), eta.get("Minute", 60)
    # 0 (month/day), 24 (hour) and 60 (minute) mean "not available".
    if not month or not day or hour > 23 or minute > 59:
        return None
    for year in (now.year, now.year + 1, now.year - 1):
        try:
            candidate = datetime(year, month, day, hour, minute, tzinfo=UTC)
        except ValueError:  # e.g. 29 February in a non-leap year
            continue
        if abs(candidate - now) <= timedelta(days=183):
            return candidate
    return None


@dataclass
class ShipData:
    """Latest known state of a single tracked vessel."""

    mmsi: str
    name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    sog: float | None = None
    cog: float | None = None
    true_heading: int | None = None
    navigational_status: int | None = None
    ship_type: int | None = None
    call_sign: str | None = None
    imo: int | None = None
    destination: str | None = None
    eta: datetime | None = None
    length: int | None = None
    width: int | None = None
    draught: float | None = None
    last_position_update: datetime | None = None
    last_static_update: datetime | None = None
    # Area subentry this vessel is assigned to (the first one it was seen in).
    area_id: str | None = None


@dataclass
class AreaFilter:
    """Resolved filter of one monitored area subentry."""

    bounding_boxes: list[list[list[float]]]
    mmsi: frozenset[str]


class AISStreamClient:
    """Owns the persistent websocket connection to aisstream.io."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        api_key: str,
        areas: dict[str, AreaFilter],
    ) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.ships: dict[str, ShipData] = {}
        self.available = False
        self.areas = areas
        self.bounding_boxes = [
            box for area in areas.values() for box in area.bounding_boxes
        ]
        mmsi_filter = sorted({mmsi for area in areas.values() for mmsi in area.mmsi})
        self.messages_received = 0
        self.last_message_at: datetime | None = None
        # Vessels restored from the registry haven't reported since this.
        self.started_at = dt_util.utcnow()

        self._api_key = api_key
        self._mmsi_filter = mmsi_filter or None
        self._session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._task: asyncio.Task | None = None
        self._stopping = False

    def start(self) -> None:
        """Start the background connection task."""
        self._task = self.hass.loop.create_task(self._run())

    async def stop(self) -> None:
        """Stop the connection task and close the session."""
        self._stopping = True
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    def forget_ship(self, mmsi: str) -> None:
        """Drop a vessel so it is set up from scratch when seen again."""
        if self.ships.pop(mmsi, None) is not None:
            async_dispatcher_send(
                self.hass, f"{SIGNAL_SHIP_REMOVED}_{self.entry_id}", mmsi
            )

    def _subscribe_message(self) -> dict:
        # Deliberately not sending FilterMessageTypes: aisstream.io only has a
        # confirmed single-value example (["PositionReport"]) for that field,
        # and unfiltered subscriptions are the reliably documented case.
        # Unwanted message types are discarded client-side in _handle_message.
        message: dict = {
            "APIKey": self._api_key,
            "BoundingBoxes": self.bounding_boxes,
        }
        if self._mmsi_filter:
            message["FiltersShipMMSI"] = self._mmsi_filter
        return message

    async def _run(self) -> None:
        self._session = aiohttp.ClientSession()
        delay = RECONNECT_DELAY_MIN
        try:
            while not self._stopping:
                connected_at = dt_util.utcnow()
                try:
                    await self._connect_and_listen()
                except asyncio.CancelledError:
                    raise
                except aiohttp.WSServerHandshakeError as err:
                    if err.status == 429:
                        _LOGGER.warning(
                            "aisstream.io rejected the connection with HTTP 429"
                            " (too many connections or rate-limited); make sure"
                            " no other client uses this account's connection"
                            " slots"
                        )
                    else:
                        _LOGGER.warning("aisstream.io connection error: %s", err)
                except Exception as err:  # noqa: BLE001
                    _LOGGER.warning("aisstream.io connection error: %s", err)
                finally:
                    self.available = False

                if self._stopping:
                    break
                # Only reset the backoff after a connection that actually held
                # up - aisstream.io rate-limits (HTTP 429) accounts and IPs
                # that reconnect in a tight loop after immediate closes.
                if (
                    dt_util.utcnow() - connected_at
                ).total_seconds() >= STABLE_CONNECTION_SECONDS:
                    delay = RECONNECT_DELAY_MIN
                await asyncio.sleep(delay)
                delay = min(delay * 2, RECONNECT_DELAY_MAX)
        finally:
            await self._session.close()

    async def _connect_and_listen(self) -> None:
        # aisstream.io requires permessage-deflate (compress=15) to serve the
        # full message bandwidth; without it little or no data arrives.
        async with self._session.ws_connect(
            AISSTREAM_WS_URL, heartbeat=30, compress=15
        ) as ws:
            self._ws = ws
            await ws.send_json(self._subscribe_message())
            self.available = True
            _LOGGER.info(
                "Subscribed to aisstream.io with bounding boxes %s%s",
                self.bounding_boxes,
                f" and MMSI filter {self._mmsi_filter}" if self._mmsi_filter else "",
            )

            async for msg in ws:
                if self._stopping:
                    break
                if msg.type in (aiohttp.WSMsgType.TEXT, aiohttp.WSMsgType.BINARY):
                    # aisstream.io delivers its JSON payloads as binary frames.
                    self.messages_received += 1
                    self.last_message_at = dt_util.utcnow()
                    self._handle_message(json.loads(msg.data))
                elif msg.type in (
                    aiohttp.WSMsgType.ERROR,
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.CLOSING,
                ):
                    break

    def _handle_message(self, data: dict) -> None:
        if error := data.get("error"):
            _LOGGER.error("aisstream.io reported an error: %s", error)
            return

        message_type = data.get("MessageType")
        if message_type == "SubscriptionConfirmation":
            _LOGGER.debug("aisstream.io confirmed subscription: %s", data)
            return

        metadata = data.get("MetaData") or {}
        mmsi = str(metadata.get("MMSI") or "")
        if not mmsi:
            return

        message = data.get("Message") or {}
        ship = self.ships.setdefault(mmsi, ShipData(mmsi=mmsi))

        if ship_name := metadata.get("ShipName"):
            ship.name = ship_name.strip() or ship.name

        now = dt_util.utcnow()

        if message_type in POSITION_MESSAGE_TYPES:
            report = message.get(message_type) or {}
            ship.latitude = metadata.get("latitude", report.get("Latitude"))
            ship.longitude = metadata.get("longitude", report.get("Longitude"))
            ship.sog = _available(report.get("Sog"), SOG_NOT_AVAILABLE)
            ship.cog = _available(report.get("Cog"), COG_NOT_AVAILABLE)
            ship.true_heading = _available(
                report.get("TrueHeading"), HEADING_NOT_AVAILABLE
            )
            if "NavigationalStatus" in report:
                # Only class A vessels report a navigational status.
                ship.navigational_status = report["NavigationalStatus"]
            if message_type == "ExtendedClassBPositionReport":
                self._apply_static(ship, report, type_key="Type")
            ship.last_position_update = now
        elif message_type == "ShipStaticData":
            static = message.get("ShipStaticData") or {}
            self._apply_static(ship, static, type_key="Type")
            ship.destination = (
                static.get("Destination") or ""
            ).strip() or ship.destination
            ship.imo = static.get("ImoNumber") or ship.imo
            if draught := static.get("MaximumStaticDraught"):
                ship.draught = draught
            if "Eta" in static:
                ship.eta = _parse_eta(static["Eta"], now)
            ship.last_static_update = now
        elif message_type == "StaticDataReport":
            # Class B static data comes in two parts: A carries the name,
            # B the type, call sign and dimensions.
            static = message.get("StaticDataReport") or {}
            if (part_b := static.get("ReportB") or {}).get("Valid"):
                self._apply_static(ship, part_b, type_key="ShipType")
            ship.last_static_update = now
        else:
            return

        if ship.area_id is None:
            # Entities are only created once the vessel can be tied to an
            # area, so they get removed together with that area.
            ship.area_id = self._assign_area(ship)
            if ship.area_id is not None:
                async_dispatcher_send(
                    self.hass, f"{SIGNAL_NEW_SHIP}_{self.entry_id}", mmsi
                )
            return

        async_dispatcher_send(self.hass, f"{SIGNAL_SHIP_UPDATE}_{mmsi}")

    @staticmethod
    def _apply_static(ship: ShipData, static: dict, type_key: str) -> None:
        """Copy the static fields shared by class A and class B reports."""
        ship.call_sign = (static.get("CallSign") or "").strip() or ship.call_sign
        ship.ship_type = static.get(type_key) or ship.ship_type
        dimension = static.get("Dimension") or {}
        # A/B are the distances from the GPS antenna to bow/stern, C/D to
        # port/starboard; zero means "not available".
        length = (dimension.get("A") or 0) + (dimension.get("B") or 0)
        width = (dimension.get("C") or 0) + (dimension.get("D") or 0)
        ship.length = length or ship.length
        ship.width = width or ship.width

    def _assign_area(self, ship: ShipData) -> str | None:
        """Return the area a vessel belongs to: MMSI lists first, then boxes."""
        for area_id, area in self.areas.items():
            if ship.mmsi in area.mmsi:
                return area_id

        if ship.latitude is None or ship.longitude is None:
            return None
        for area_id, area in self.areas.items():
            if area.mmsi:
                continue
            if any(
                point_in_box(ship.latitude, ship.longitude, [box])
                for box in area.bounding_boxes
            ):
                return area_id
        return None
