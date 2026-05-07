"""Plateforme cover pour les volets Dooya RF433."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.components.radio_frequency import (
    ModulationType,
    async_send_command,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DEFAULT_CHECK_DOWN, DEFAULT_CHECK_STOP, DEFAULT_CHECK_UP, DOMAIN
from .dooya_protocol import (
    BUTTON_DOWN,
    BUTTON_STOP,
    BUTTON_UP,
    DOOYA_FREQUENCY_HZ,
    DooyaData,
    encode_dooya,
)
from .entity import DooyaBaseEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configurer les entités cover Dooya depuis un config entry."""
    async_add_entities([DooyaCover(config_entry)])


class RadioFrequencyCommand:
    """Commande RF433 OOK pour le protocole Dooya.

    Encapsule les timings OOK à envoyer via la plateforme radio_frequency de HA.
    La fréquence est 433.92 MHz, modulation OOK.
    """

    def __init__(self, data: DooyaData) -> None:
        """Initialiser la commande depuis des données Dooya."""
        self._data = data
        self.frequency: int = DOOYA_FREQUENCY_HZ
        self.modulation: ModulationType = ModulationType.OOK

    def get_raw_timings(self) -> list[int]:
        """Retourner la liste de timings OOK en µs (HIGH, LOW alternés)."""
        return encode_dooya(self._data)


class DooyaCover(DooyaBaseEntity, CoverEntity, RestoreEntity):
    """Volet Dooya RF433 contrôlé via la plateforme radio_frequency de HA.

    État supposé (assumed_state) — aucun retour d'état du volet.
    Fonctionnalités : ouvrir, fermer, stopper.

    Compatibilité transmetteurs :
    - ESPHome + CC1101 (via radio_frequency platform)
    - Broadlink RM4 Pro (via radio_frequency platform)
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
        await self._async_send(BUTTON_UP, DEFAULT_CHECK_UP)
        self._is_closed = False
        self.async_write_ha_state()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Fermer le volet (commande DOWN, button=3)."""
        await self._async_send(BUTTON_DOWN, DEFAULT_CHECK_DOWN)
        self._is_closed = True
        self.async_write_ha_state()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stopper le volet (commande STOP, button=5)."""
        await self._async_send(BUTTON_STOP, DEFAULT_CHECK_STOP)
        # L'état n'est pas connu après un stop
        self.async_write_ha_state()

    async def _async_send(self, button: int, check: int) -> None:
        """Encoder et envoyer la commande RF via la plateforme radio_frequency."""
        registry = er.async_get(self.hass)
        transmitter_entity_id = self._get_transmitter_entity_id(registry)

        if transmitter_entity_id is None:
            _LOGGER.error(
                "Transmetteur RF introuvable (UUID=%s) pour le volet %s",
                self._transmitter_uuid,
                self.name,
            )
            return

        data = DooyaData(
            id=self._dooya_id,
            channel=self._channel,
            button=button,
            check=check,
        )
        command = RadioFrequencyCommand(data)

        try:
            await async_send_command(self.hass, transmitter_entity_id, command)
        except Exception:  # noqa: BLE001
            _LOGGER.exception(
                "Erreur lors de l'envoi de la commande RF au volet %s", self.name
            )
