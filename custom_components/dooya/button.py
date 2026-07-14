"""Plateforme button pour les volets Dooya RF433.

Expose les actions de recalage comme entités sur l'appareil du volet,
utilisables depuis la page appareil et les automatisations sans appel de
service explicite.
"""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import DooyaBaseEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configurer les boutons Dooya depuis un config entry."""
    async_add_entities(
        [
            DooyaMarkOpenButton(config_entry),
            DooyaMarkClosedButton(config_entry),
        ]
    )


class DooyaButtonBase(DooyaBaseEntity, ButtonEntity):
    """Bouton lié au volet Dooya de la même entrée de configuration."""

    _attr_entity_category = EntityCategory.CONFIG
    translation_key: str

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialiser le bouton."""
        super().__init__(config_entry)
        self._attr_translation_key = self.translation_key
        self._attr_unique_id = f"{config_entry.entry_id}_{self.translation_key}"

    @property
    def _cover(self):
        """Retourner l'entité cover de cette entrée (ou None)."""
        cover = (
            self.hass.data.get(DOMAIN, {})
            .get(self._config_entry.entry_id, {})
            .get("cover")
        )
        if cover is None:
            _LOGGER.warning(
                "%s: cover entity not ready, button press ignored",
                self._cover_name,
            )
        return cover


class DooyaMarkOpenButton(DooyaButtonBase):
    """Recale la position estimée à 100 % sans émettre de trame RF."""

    translation_key = "mark_open"
    _attr_icon = "mdi:arrow-collapse-up"

    async def async_press(self) -> None:
        """Marquer le volet comme ouvert."""
        if (cover := self._cover) is not None:
            cover.async_mark_open()


class DooyaMarkClosedButton(DooyaButtonBase):
    """Recale la position estimée à 0 % sans émettre de trame RF."""

    translation_key = "mark_closed"
    _attr_icon = "mdi:arrow-collapse-down"

    async def async_press(self) -> None:
        """Marquer le volet comme fermé."""
        if (cover := self._cover) is not None:
            cover.async_mark_closed()
