"""Entité de base pour les volets Dooya RF."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import slugify

from .const import (
    CONF_CHANNEL,
    CONF_CHECK,
    CONF_COVER_NAME,
    CONF_DOOYA_ID,
    CONF_ESPHOME_DEVICE,
    DOMAIN,
)
from .device_match import is_esphome_device

_LOGGER = logging.getLogger(__name__)


class DooyaBaseEntity(Entity):
    """Entité de base pour les volets Dooya.

    Stocke les paramètres appris/manuels d'un volet Dooya.

    Les commandes sont envoyées par la plateforme cover via le service/action
    ESPHome `transmit_dooya`.

    Availability mirrors the configured ESPHome gateway: when every entity of
    the gateway device is unavailable (node offline), Dooya entities become
    unavailable too instead of failing silently on transmit.
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
        self._cover_name: str = data[CONF_COVER_NAME]

        self._gateway_entity_ids: list[str] = []

        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
            "name": self._cover_name,
            "manufacturer": "Dooya",
            "model": "RF433 Cover",
        }

    @property
    def _esphome_device(self) -> str:
        """Slug du device ESPHome configuré (les options priment sur data)."""
        return self._config_entry.options.get(
            CONF_ESPHOME_DEVICE,
            self._config_entry.data.get(CONF_ESPHOME_DEVICE, ""),
        )

    @property
    def available(self) -> bool:
        """Refléter la disponibilité de la passerelle ESPHome."""
        if not self._gateway_entity_ids:
            return True
        return any(
            (state := self.hass.states.get(entity_id)) is not None
            and state.state != "unavailable"
            for entity_id in self._gateway_entity_ids
        )

    async def async_added_to_hass(self) -> None:
        """Suivre la disponibilité de la passerelle ESPHome."""
        await super().async_added_to_hass()
        try:
            self._gateway_entity_ids = self._resolve_gateway_entities()
        except Exception:  # availability tracking is best-effort by contract
            _LOGGER.warning(
                "%s: could not resolve the ESPHome gateway, "
                "availability tracking disabled",
                self._cover_name,
                exc_info=True,
            )
            self._gateway_entity_ids = []
        if self._gateway_entity_ids:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass,
                    self._gateway_entity_ids,
                    self._handle_gateway_state_change,
                )
            )

    def _handle_gateway_state_change(self, _event) -> None:
        """Répercuter un changement d'état de la passerelle sur l'entité."""
        self.async_write_ha_state()

    def _resolve_gateway_entities(self) -> list[str]:
        """Trouver les entités du device ESPHome configuré.

        Le config entry ne stocke que le slug du device (ex.
        `volets-dooya-rf433`) ; on le fait correspondre au nom du device
        ESPHome dans le registre. Si rien ne correspond, l'entité reste
        toujours disponible (aucune régression).
        """
        gateway_slug = slugify(self._esphome_device)
        if not gateway_slug:
            return []

        device_registry = dr.async_get(self.hass)
        entity_registry = er.async_get(self.hass)

        for device in device_registry.devices.values():
            if not is_esphome_device(device.identifiers):
                continue
            if slugify(device.name or "") != gateway_slug:
                continue
            entries = er.async_entries_for_device(
                entity_registry, device.id, include_disabled_entities=False
            )
            entity_ids = [entry.entity_id for entry in entries]
            _LOGGER.debug(
                "%s: availability linked to gateway %s (%d entities)",
                self._cover_name,
                self._esphome_device,
                len(entity_ids),
            )
            return entity_ids

        _LOGGER.debug(
            "%s: ESPHome gateway %s not found in device registry, "
            "availability tracking disabled",
            self._cover_name,
            self._esphome_device,
        )
        return []
