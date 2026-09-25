"""WebSocket client that maintains the connection to aisstream.io."""
from __future__ import annotations

import asyncio
import contextlib
import json
from dataclasses import dataclass
from datetime import datetime
import logging

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

from .const import (
    AISSTREAM_WS_URL,
    RECONNECT_DELAY_MAX,
    RECONNECT_DELAY_MIN,
    SIGNAL_NEW_SHIP,
    SIGNAL_SHIP_UPDATE,
    STABLE_CONNECTION_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


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
    destination: str | None = None
    last_position_update: datetime | None = None
    last_static_update: datetime | None = None


class AISStreamClient:
    """Owns the persistent websocket connection to aisstream.io."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        api_key: str,
        bounding_boxes: list[list[list[float]]],
        mmsi_filter: list[str] | None,
    ) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.ships: dict[str, ShipData] = {}
        self.available = False
        self.bounding_boxes = bounding_boxes
        self.messages_received = 0
        self.last_message_at: datetime | None = None

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
        is_new = mmsi not in self.ships
        ship = self.ships.setdefault(mmsi, ShipData(mmsi=mmsi))

        if ship_name := metadata.get("ShipName"):
            ship.name = ship_name.strip() or ship.name

        now = dt_util.utcnow()

        if message_type == "PositionReport":
            report = message.get("PositionReport") or {}
            ship.latitude = metadata.get("latitude", report.get("Latitude"))
            ship.longitude = metadata.get("longitude", report.get("Longitude"))
            ship.sog = report.get("Sog")
            ship.cog = report.get("Cog")
            ship.true_heading = report.get("TrueHeading")
            ship.navigational_status = report.get("NavigationalStatus")
            ship.last_position_update = now
        elif message_type == "ShipStaticData":
            static = message.get("ShipStaticData") or {}
            ship.call_sign = static.get("CallSign", "").strip() or ship.call_sign
            ship.destination = static.get("Destination", "").strip() or ship.destination
            ship.ship_type = static.get("Type")
            ship.last_static_update = now
        else:
            return

        if is_new:
            async_dispatcher_send(
                self.hass, f"{SIGNAL_NEW_SHIP}_{self.entry_id}", mmsi
            )
        else:
            async_dispatcher_send(self.hass, f"{SIGNAL_SHIP_UPDATE}_{mmsi}")
