"""Event platform for Dooya RF433 shutters: the physical remote's presses.

The integration already hears the remote (to keep the position estimate in
step); this entity hands each press to automations, so the remote's buttons
can do more than move the shutter: "down" in the evening can also switch on
a lamp.

Only presses heard from a remote fire it. A command sent by Home Assistant,
heard back by a node, is an echo and fires nothing (see `cover.py`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.event import EventDeviceClass, EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import remote_press_signal
from .dooya_protocol import BUTTON_DOWN, BUTTON_STOP, BUTTON_UP
from .entity import DooyaBaseEntity

if TYPE_CHECKING:
    from . import DooyaConfigEntry

# The remote's own words, not the shutter's: on an awning "down" opens, and
# an automation written against the remote should read like the remote.
EVENT_TYPES: dict[int, str] = {
    BUTTON_UP: "up",
    BUTTON_STOP: "stop",
    BUTTON_DOWN: "down",
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DooyaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the remote event entity of a Dooya shutter."""
    async_add_entities([DooyaRemoteEvent(config_entry)])


class DooyaRemoteEvent(DooyaBaseEntity, EventEntity):
    """Fires once per press of the physical remote on this shutter."""

    _attr_device_class = EventDeviceClass.BUTTON
    _attr_translation_key = "remote"

    def __init__(self, config_entry: DooyaConfigEntry) -> None:
        """Initialize the event entity."""
        super().__init__(config_entry)
        self._attr_event_types = list(EVENT_TYPES.values())
        self._attr_unique_id = f"{config_entry.entry_id}_remote"

    async def async_added_to_hass(self) -> None:
        """Listen to the presses the cover hears for this entry."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                remote_press_signal(self._config_entry.entry_id),
                self._handle_press,
            )
        )

    @callback
    def _handle_press(self, button: int) -> None:
        """Fire the event for one press."""
        if (event_type := EVENT_TYPES.get(button)) is None:
            return
        self._trigger_event(event_type)
        self.async_write_ha_state()
