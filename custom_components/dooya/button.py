"""Button platform for Dooya RF433 shutters.

Exposes the recalibration actions as entities on the shutter's device, usable
from the device page and from automations without an explicit service call.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_FAVORITE_POSITION
from .entity import DooyaBaseEntity

if TYPE_CHECKING:
    from . import DooyaConfigEntry
    from .cover import DooyaCover

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DooyaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Dooya buttons from a config entry."""
    entities: list[DooyaButtonBase] = [
        DooyaMarkOpenButton(config_entry),
        DooyaMarkClosedButton(config_entry),
        DooyaCalibrateUpButton(config_entry),
        DooyaCalibrateDownButton(config_entry),
    ]
    # The favorite button only exists when a favorite position is set in
    # the options (the entry reloads on options change, so it appears and
    # disappears without restart).
    if config_entry.options.get(CONF_FAVORITE_POSITION) is not None:
        entities.append(DooyaFavoriteButton(config_entry))
    async_add_entities(entities)


class DooyaButtonBase(DooyaBaseEntity, ButtonEntity):
    """Button bound to the Dooya shutter of the same config entry."""

    _attr_entity_category = EntityCategory.CONFIG
    translation_key: str

    def __init__(self, config_entry: DooyaConfigEntry) -> None:
        """Initialize the button."""
        super().__init__(config_entry)
        self._attr_translation_key = self.translation_key
        self._attr_unique_id = f"{config_entry.entry_id}_{self.translation_key}"

    @property
    def _cover(self) -> DooyaCover | None:
        """Return the cover entity of this entry, or None when not ready."""
        cover = self._config_entry.runtime_data.cover
        if cover is None:
            _LOGGER.warning(
                "%s: cover entity not ready, button press ignored",
                self._cover_name,
            )
        return cover


class DooyaMarkOpenButton(DooyaButtonBase):
    """Resync the estimate to 100% without transmitting an RF frame."""

    translation_key = "mark_open"
    _attr_icon = "mdi:arrow-collapse-up"

    async def async_press(self) -> None:
        """Mark the shutter as open."""
        if (cover := self._cover) is not None:
            cover.async_mark_open()


class DooyaMarkClosedButton(DooyaButtonBase):
    """Resync the estimate to 0% without transmitting an RF frame."""

    translation_key = "mark_closed"
    _attr_icon = "mdi:arrow-collapse-down"

    async def async_press(self) -> None:
        """Mark the shutter as closed."""
        if (cover := self._cover) is not None:
            cover.async_mark_closed()


class DooyaCalibrateUpButton(DooyaButtonBase):
    """Measure the full opening time (the shutter must be closed first)."""

    translation_key = "calibrate_up"
    _attr_icon = "mdi:timer-play-outline"

    async def async_press(self) -> None:
        """Start measuring the opening time."""
        if (cover := self._cover) is not None:
            await cover.async_start_calibration(1)


class DooyaCalibrateDownButton(DooyaButtonBase):
    """Measure the full closing time (the shutter must be open first)."""

    translation_key = "calibrate_down"
    _attr_icon = "mdi:timer-stop-outline"

    async def async_press(self) -> None:
        """Start measuring the closing time."""
        if (cover := self._cover) is not None:
            await cover.async_start_calibration(-1)


class DooyaFavoriteButton(DooyaButtonBase):
    """Send the shutter to its configured favorite position."""

    translation_key = "favorite"
    _attr_icon = "mdi:star"
    _attr_entity_category = None  # control, not configuration

    async def async_press(self) -> None:
        """Go to the favorite position."""
        favorite = self._config_entry.options.get(CONF_FAVORITE_POSITION)
        if favorite is None or (cover := self._cover) is None:
            return
        await cover.async_set_cover_position(position=int(favorite))
