"""Plateforme cover pour les volets Dooya RF433.

Principe de fonctionnement :
- HA appelle le service ESPHome `transmit_dooya` via l'intégration esphome
- ESPHome exécute la lambda qui appelle remote_transmitter.transmit_dooya
- Service name : esphome.{device_slug}_transmit_dooya
  ex : esphome.volets_dooya_rf433_transmit_dooya

Le device_slug est calculé depuis CONF_ESPHOME_DEVICE (tirets → underscores).
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_ESPHOME_DEVICE,
    DEFAULT_CHECK_DOWN,
    DEFAULT_CHECK_STOP,
    DEFAULT_CHECK_UP,
)
from .dooya_protocol import BUTTON_DOWN, BUTTON_STOP, BUTTON_UP
from .entity import DooyaBaseEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configurer les entités cover Dooya depuis un config entry."""
    async_add_entities([DooyaCover(config_entry)])


class DooyaCover(DooyaBaseEntity, CoverEntity, RestoreEntity):
    """Volet Dooya RF433.

    Commande le volet via un service natif ESPHome.

    État supposé (assumed_state) — aucun retour d'état du volet physique.
    """

    _attr_device_class = CoverDeviceClass.SHUTTER
    _attr_assumed_state = True
    _attr_supported_features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
    )

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialiser le volet Dooya."""
        super().__init__(config_entry)
        self._is_closed: bool | None = None

    @property
    def is_closed(self) -> bool | None:
        """Retourner l'état fermé supposé."""
        return self._is_closed

    async def async_added_to_hass(self) -> None:
        """Restaurer l'état précédent depuis le storage HA."""
        if (last_state := await self.async_get_last_state()) is not None:
            if last_state.state == "closed":
                self._is_closed = True
            elif last_state.state == "open":
                self._is_closed = False

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Ouvrir le volet (commande UP, button=1)."""
        await self._async_transmit(BUTTON_UP, DEFAULT_CHECK_UP)
        self._is_closed = False
        self.async_write_ha_state()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Fermer le volet (commande DOWN, button=3)."""
        await self._async_transmit(BUTTON_DOWN, DEFAULT_CHECK_DOWN)
        self._is_closed = True
        self.async_write_ha_state()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stopper le volet (commande STOP, button=5)."""
        await self._async_transmit(BUTTON_STOP, DEFAULT_CHECK_STOP)
        self.async_write_ha_state()

    async def _async_transmit(self, button: int, check: int) -> None:
        """Appeler le service ESPHome transmit_dooya.

        Service cible : esphome.{device_slug}_transmit_dooya
        Variables : dooya_id (int), channel (int), btn (int), check (int)
        """
        service_name = self._resolve_service_name()
        if service_name is None:
            return
        _LOGGER.debug(
            "esphome.%s → id=%08X channel=%d button=%d check=%d",
            service_name,
            self._dooya_id,
            self._channel,
            button,
            check,
        )
        if not self.hass.services.has_service("esphome", service_name):
            _LOGGER.error(
                "Service ESPHome introuvable: esphome.%s. "
                "Redémarrer Home Assistant et vérifier que les appels de services ESPHome sont autorisés.",
                service_name,
            )
            return
        await self.hass.services.async_call(
            "esphome",
            service_name,
            {
                "dooya_id": self._dooya_id,
                "channel": self._channel,
                "btn": button,
                "check": check,
            },
            blocking=True,
        )

    def _resolve_service_name(self) -> str | None:
        """Déterminer le nom du service ESPHome à appeler."""
        device = self._config_entry.data.get(CONF_ESPHOME_DEVICE, "")
        if not device:
            _LOGGER.error(
                "Aucun device ESPHome configuré pour %s. "
                "Reconfigurer l'entrée Dooya avec le bon device.",
                self._attr_name,
            )
            return None

        service_name = f"{device.replace('-', '_')}_transmit_dooya"
        if self.hass.services.has_service("esphome", service_name):
            return service_name

        _LOGGER.error(
            "Service ESPHome introuvable: esphome.%s. "
            "Vérifier le nom du device ESPHome configuré.",
            service_name,
        )
        return None
