"""Sensor platform for Dooya RF433 shutters: how far to trust the position.

The motor reports nothing, so the position is an estimate that drifts a
little with every move stopped between the end stops. The cover already
exposes that as its `position_confidence` attribute; this diagnostic sensor
gives it an entity of its own, for a dashboard or an automation that sends a
drifting shutter to an end stop to resync it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import cover_state_signal, is_group_entry
from .entity import DooyaBaseEntity

if TYPE_CHECKING:
    from . import DooyaConfigEntry

CONFIDENCE_LEVELS = ["high", "medium", "low"]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DooyaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the position confidence sensor of a Dooya shutter."""
    if is_group_entry(config_entry):
        # The group cover keeps no position estimate, so nothing to trust.
        return
    async_add_entities([DooyaPositionConfidence(config_entry)])


class DooyaPositionConfidence(DooyaBaseEntity, SensorEntity):
    """Follows the cover's confidence in its own estimated position."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "position_confidence"

    def __init__(self, config_entry: DooyaConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(config_entry)
        self._attr_options = CONFIDENCE_LEVELS
        self._attr_unique_id = f"{config_entry.entry_id}_position_confidence"

    @property
    def native_value(self) -> str | None:
        """Return the cover's confidence, or None before the cover is up."""
        cover = self._config_entry.runtime_data.cover
        return None if cover is None else cover.position_confidence

    async def async_added_to_hass(self) -> None:
        """Follow every state the cover writes."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                cover_state_signal(self._config_entry.entry_id),
                self._handle_cover_state,
            )
        )

    @callback
    def _handle_cover_state(self) -> None:
        """Write the sensor's state after the cover's."""
        self.async_write_ha_state()
