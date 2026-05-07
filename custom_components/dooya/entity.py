"""Entité de base pour les volets Dooya RF."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import Entity

from .const import (
    CONF_CHANNEL,
    CONF_CHECK,
    CONF_COVER_NAME,
    CONF_DOOYA_ID,
    CONF_TRANSMITTER,
    DOMAIN,
)


class DooyaBaseEntity(Entity):
    """Entité de base pour les volets Dooya.

    Fournit les attributs communs et la résolution du transmetteur RF
    depuis son UUID (résistant aux renommages d'entité).
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
        self._transmitter_uuid: str = data[CONF_TRANSMITTER]
        cover_name: str = data[CONF_COVER_NAME]

        self._attr_name = cover_name
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
            "name": cover_name,
            "manufacturer": "Dooya",
            "model": "RF433 Cover",
        }

    def _get_transmitter_entity_id(self, registry: er.EntityRegistry) -> str | None:
        """Résoudre l'entity_id du transmetteur depuis son UUID.

        Utilise l'UUID stocké pour être résistant aux renommages.
        """
        entry = registry.async_get_entry(self._transmitter_uuid)  # type: ignore[arg-type]
        if entry is None:
            return None
        return entry.entity_id
