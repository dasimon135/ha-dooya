"""Plateforme cover pour les volets Dooya RF433.

Principe de fonctionnement :
- HA fire un événement `dooya.transmit` sur le bus interne
- ESPHome écoute via `on_homeassistant_event: dooya.transmit`
- ESPHome appelle `remote_transmitter.transmit_dooya` avec les paramètres

Avantage : aucune dépendance à radio_frequency, compatible avec
tout transmetteur ESPHome exposant le handler d'événement.
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
    DEFAULT_CHECK_DOWN,
    DEFAULT_CHECK_STOP,
    DEFAULT_CHECK_UP,
    EVENT_DOOYA_TRANSMIT,
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

    Commande le volet via l'événement HA `dooya.transmit` qui est
    intercepté par ESPHome (on_homeassistant_event).

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
        self._fire_transmit(BUTTON_UP, DEFAULT_CHECK_UP)
        self._is_closed = False
        self.async_write_ha_state()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Fermer le volet (commande DOWN, button=3)."""
        self._fire_transmit(BUTTON_DOWN, DEFAULT_CHECK_DOWN)
        self._is_closed = True
        self.async_write_ha_state()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stopper le volet (commande STOP, button=5)."""
        self._fire_transmit(BUTTON_STOP, DEFAULT_CHECK_STOP)
        self.async_write_ha_state()

    def _fire_transmit(self, button: int, check: int) -> None:
        """Tirer l'événement dooya.transmit sur le bus HA.

        ESPHome intercepte cet événement via on_homeassistant_event
        et déclenche remote_transmitter.transmit_dooya.

        Format de l'événement :
          id      : identifiant hex 8 caractères, ex "00D1C917"
          channel : canal (int)
          button  : bouton (1=up, 3=down, 5=stop)
          check   : code de contrôle
          device  : slug du device ESPHome (filtre optionnel)
        """
        self.hass.bus.async_fire(
            EVENT_DOOYA_TRANSMIT,
            {
                "id": f"{self._dooya_id:08X}",
                "channel": self._channel,
                "button": button,
                "check": check,
                "device": self._esphome_device,
            },
        )
        _LOGGER.debug(
            "dooya.transmit → id=%08X channel=%d button=%d check=%d device=%s",
            self._dooya_id,
            self._channel,
            button,
            check,
            self._esphome_device,
        )
