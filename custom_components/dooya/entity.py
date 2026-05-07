"""Entité de base pour les volets Dooya RF."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import Entity

from .const import (
    CONF_CHANNEL,
    CONF_CHECK,
    CONF_COVER_NAME,
    CONF_DOOYA_ID,
    CONF_ESPHOME_DEVICE,
    DOMAIN,
)


class DooyaBaseEntity(Entity):
    """Entité de base pour les volets Dooya.

    Transmet les commandes via l'événement HA `dooya.transmit`
    écouté par ESPHome (on_homeassistant_event).
    """

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialiser l'entité Dooya."""
        self._config_entry = config_entry
        self._attr_unique_id = config_entry.entry_id

        data = config_entry.data
        self._dooya_id: int = data[CONF_DOOYA_ID]
        self._channel: int = data[CONF_CHANNEL]
        self._check: int = data[CONF_CHECK]
        self._esphome_device: str = data.get(CONF_ESPHOME_DEVICE, "")
        cover_name: str = data[CONF_COVER_NAME]

        self._attr_name = cover_name
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
            "name": cover_name,
            "manufacturer": "Dooya",
            "model": "RF433 Cover",
        }
