"""Button platform for aisstream.io."""
from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .cleanup import async_remove_stale_vessels
from .const import DOMAIN, PRESENCE_TIMEOUT_MINUTES, SUBENTRY_TYPE_AREA
from .coordinator import AISStreamClient
from .entity import area_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up one "remove stale vessels" button per monitored area."""
    client: AISStreamClient = hass.data[DOMAIN][entry.entry_id]

    for subentry_id, subentry in entry.subentries.items():
        if subentry.subentry_type != SUBENTRY_TYPE_AREA:
            continue
        async_add_entities(
            [AISStreamRemoveStaleButton(client, entry, subentry_id, subentry)],
            config_subentry_id=subentry_id,
        )


class AISStreamRemoveStaleButton(ButtonEntity):
    """Removes the area's vessels that are no longer present."""

    _attr_has_entity_name = True
    _attr_translation_key = "remove_stale_vessels"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:broom"

    def __init__(
        self,
        client: AISStreamClient,
        entry: ConfigEntry,
        subentry_id: str,
        subentry: ConfigSubentry,
    ) -> None:
        self._client = client
        self._entry = entry
        self._subentry_id = subentry_id
        self._subentry = subentry
        self._attr_unique_id = f"{subentry_id}_remove_stale_vessels"

    @property
    def device_info(self) -> DeviceInfo:
        return area_device_info(self._subentry_id, self._subentry)

    async def async_press(self) -> None:
        """Remove vessels without a position report in the presence window.

        Vessels not seen since the last restart count as stale right away.
        """
        removed = async_remove_stale_vessels(
            self.hass,
            self._entry,
            self._client,
            timedelta(minutes=PRESENCE_TIMEOUT_MINUTES),
            subentry_id=self._subentry_id,
        )
        _LOGGER.info(
            "Removed %s stale vessel(s) from area '%s'", removed, self._subentry.title
        )
