"""Plateforme cover pour les volets Dooya RF433."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging
from time import monotonic
from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.restore_state import RestoreEntity
import voluptuous as vol

from .const import (
    BROADCAST_CHANNEL,
    CONF_ESPHOME_DEVICE,
    CONF_REPEAT_COUNT,
    CONF_TRAVEL_TIME_DOWN,
    CONF_TRAVEL_TIME_UP,
    DEFAULT_CHECK_DOWN,
    DEFAULT_CHECK_STOP,
    DEFAULT_CHECK_UP,
    DEFAULT_REPEAT_COUNT,
    DEFAULT_TRAVEL_TIME_DOWN,
    DEFAULT_TRAVEL_TIME_UP,
    DOMAIN,
    ECHO_SUPPRESS_WINDOW_SEC,
    EVENT_DOOYA_RECEIVED,
)
from .dooya_protocol import BUTTON_DOWN, BUTTON_STOP, BUTTON_UP
from .echo_filter import TxEchoFilter
from .entity import DooyaBaseEntity
from .travel_calc import clamp_position, position_after, travel_duration

_LOGGER = logging.getLogger(__name__)
ATTR_CURRENT_POSITION = "current_position"
ATTR_POSITION = "position"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configurer les entités cover Dooya depuis un config entry."""
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service("mark_open", {}, "async_mark_open")
    platform.async_register_entity_service("mark_closed", {}, "async_mark_closed")
    platform.async_register_entity_service(
        "set_known_position",
        {
            vol.Required(ATTR_POSITION): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=100)
            )
        },
        "async_set_known_position",
    )
    async_add_entities([DooyaCover(config_entry)])


class DooyaCover(DooyaBaseEntity, CoverEntity, RestoreEntity):
    """Volet Dooya RF433 à position estimée par le temps."""

    _attr_device_class = CoverDeviceClass.SHUTTER
    _attr_assumed_state = True

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialiser le volet Dooya."""
        super().__init__(config_entry)
        self._attr_name = self._cover_name

        # Channel 0 is the Dooya broadcast channel ("all" button): every
        # paired shutter reacts, so a per-shutter position estimate is
        # meaningless — expose plain open/close/stop only.
        self._is_broadcast = self._channel == BROADCAST_CHANNEL
        self._attr_supported_features = (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.STOP
        )
        if not self._is_broadcast:
            self._attr_supported_features |= CoverEntityFeature.SET_POSITION

        options = config_entry.options
        self._travel_time_up = float(
            options.get(
                CONF_TRAVEL_TIME_UP,
                config_entry.data.get(CONF_TRAVEL_TIME_UP, DEFAULT_TRAVEL_TIME_UP),
            )
        )
        self._travel_time_down = float(
            options.get(
                CONF_TRAVEL_TIME_DOWN,
                config_entry.data.get(
                    CONF_TRAVEL_TIME_DOWN, DEFAULT_TRAVEL_TIME_DOWN
                ),
            )
        )
        self._repeat_count: int = int(
            options.get(
                CONF_REPEAT_COUNT,
                config_entry.data.get(CONF_REPEAT_COUNT, DEFAULT_REPEAT_COUNT),
            )
        )
        self._current_position: int | None = None
        self._movement_direction = 0
        self._movement_start_time: float | None = None
        self._movement_start_position: float | None = None
        self._target_position: int | None = None
        self._target_reached_unsub: Callable[[], None] | None = None
        self._progress_unsub: Callable[[], None] | None = None
        self._event_unsub: Callable[[], None] | None = None
        self._echo_filter = TxEchoFilter(ECHO_SUPPRESS_WINDOW_SEC)

    @property
    def is_closed(self) -> bool | None:
        """Retourner l'état fermé estimé."""
        if self._is_broadcast:
            return None
        self._refresh_position()
        if self._current_position is None:
            return None
        return self._current_position <= 0

    @property
    def current_cover_position(self) -> int | None:
        """Retourner la position estimée du volet."""
        if self._is_broadcast:
            return None
        self._refresh_position()
        return self._current_position

    @property
    def is_opening(self) -> bool:
        """Indiquer si le volet est en cours d'ouverture."""
        self._refresh_position()
        return self._movement_direction > 0

    @property
    def is_closing(self) -> bool:
        """Indiquer si le volet est en cours de fermeture."""
        self._refresh_position()
        return self._movement_direction < 0

    async def async_added_to_hass(self) -> None:
        """Restaurer l'état précédent depuis le storage HA."""
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) is not None:
            restored_position = last_state.attributes.get(ATTR_CURRENT_POSITION)
            if restored_position is not None:
                self._current_position = clamp_position(restored_position)
            elif last_state.state == "closed":
                self._current_position = 0
            elif last_state.state == "open":
                self._current_position = 100

        self._event_unsub = self.hass.bus.async_listen(
            EVENT_DOOYA_RECEIVED, self._handle_dooya_event
        )

        # Share the cover object with the button platform of this entry.
        self.hass.data.setdefault(DOMAIN, {}).setdefault(
            self._config_entry.entry_id, {}
        )["cover"] = self

    async def async_will_remove_from_hass(self) -> None:
        """Nettoyer les callbacks lors de la suppression de l'entité."""
        self._cancel_motion_callbacks()
        if self._event_unsub is not None:
            self._event_unsub()
            self._event_unsub = None
        entry_data = self.hass.data.get(DOMAIN, {}).get(self._config_entry.entry_id)
        if entry_data is not None:
            entry_data.pop("cover", None)

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Ouvrir le volet (commande UP, button=1)."""
        await self._async_transmit(BUTTON_UP, DEFAULT_CHECK_UP)
        self._start_estimated_motion(direction=1, target_position=100)

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Fermer le volet (commande DOWN, button=3)."""
        await self._async_transmit(BUTTON_DOWN, DEFAULT_CHECK_DOWN)
        self._start_estimated_motion(direction=-1, target_position=0)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stopper le volet (commande STOP, button=5)."""
        self._refresh_position()
        await self._async_transmit(BUTTON_STOP, DEFAULT_CHECK_STOP)
        self._stop_estimated_motion()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Déplacer le volet vers une position cible estimée."""
        if self._is_broadcast:
            _LOGGER.warning(
                "%s: set_position is not supported on the broadcast channel",
                self._attr_name,
            )
            return
        position = clamp_position(kwargs[ATTR_POSITION])
        self._refresh_position()

        if self._current_position is None:
            self._current_position = 0 if position >= 50 else 100

        current_position = self._current_position
        if current_position == position:
            return

        if position > current_position:
            await self._async_transmit(BUTTON_UP, DEFAULT_CHECK_UP)
            self._start_estimated_motion(direction=1, target_position=position)
            return

        await self._async_transmit(BUTTON_DOWN, DEFAULT_CHECK_DOWN)
        self._start_estimated_motion(direction=-1, target_position=position)

    @callback
    def async_mark_open(self) -> None:
        """Recaler manuellement le volet à 100%."""
        self._finalize_position(100)

    @callback
    def async_mark_closed(self) -> None:
        """Recaler manuellement le volet à 0%."""
        self._finalize_position(0)

    @callback
    def async_set_known_position(self, position: int) -> None:
        """Forcer manuellement une position connue sans envoyer de trame RF."""
        self._finalize_position(clamp_position(position))

    async def _async_transmit(self, button: int, check: int) -> None:
        """Appeler le service ESPHome transmit_dooya."""
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
        payload = {
            "dooya_id": self._dooya_id,
            "channel": self._channel,
            "btn": button,
            "check": check,
        }
        # Record before and after each call: echoes from other nodes can
        # arrive while the blocking transmit loop is still in progress.
        self._echo_filter.record_tx(button, monotonic())
        for i in range(self._repeat_count):
            if i > 0:
                await asyncio.sleep(0.1)
            await self.hass.services.async_call(
                "esphome",
                service_name,
                payload,
                blocking=True,
            )
            self._echo_filter.record_tx(button, monotonic())

    def _resolve_service_name(self) -> str | None:
        """Déterminer le nom du service ESPHome à appeler."""
        device = self._config_entry.options.get(
            CONF_ESPHOME_DEVICE,
            self._config_entry.data.get(CONF_ESPHOME_DEVICE, ""),
        )
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

    @callback
    def _handle_dooya_event(self, event: Any) -> None:
        """Synchroniser la position estimée quand la télécommande physique est utilisée."""
        data = event.data
        try:
            event_id = int(data["id"], 16) if isinstance(data["id"], str) else int(data["id"])
            event_channel = int(data["channel"])
            button = int(data["button"])
        except (KeyError, TypeError, ValueError):
            return

        if event_id != self._dooya_id:
            return
        # A broadcast frame (channel 0, remote "all" button or the HA
        # broadcast entity) moves every shutter paired with this remote.
        if event_channel != self._channel and event_channel != BROADCAST_CHANNEL:
            return

        if self._echo_filter.is_echo(button, monotonic()):
            _LOGGER.debug(
                "%s: ignoring echo of our own transmission (button=%d)",
                self._attr_name,
                button,
            )
            return

        if button == BUTTON_UP:
            self._start_estimated_motion(direction=1, target_position=100)
        elif button == BUTTON_DOWN:
            self._start_estimated_motion(direction=-1, target_position=0)
        elif button == BUTTON_STOP:
            self._refresh_position()
            self._stop_estimated_motion()

    @callback
    def _start_estimated_motion(self, direction: int, target_position: int) -> None:
        """Démarrer ou redémarrer un mouvement estimé."""
        if self._is_broadcast:
            self.async_write_ha_state()
            return
        self._refresh_position()
        self._cancel_motion_callbacks()

        if self._current_position is None:
            self._current_position = 0 if direction > 0 else 100

        start_position = self._current_position
        if start_position == target_position:
            self._finalize_position(target_position)
            return

        self._movement_direction = direction
        self._movement_start_time = monotonic()
        self._movement_start_position = float(start_position)
        self._target_position = target_position

        self._schedule_target_reached()
        self._schedule_progress_tick()
        self.async_write_ha_state()

    @callback
    def _refresh_position(self) -> None:
        """Mettre à jour la position estimée selon le temps écoulé."""
        if (
            self._movement_direction == 0
            or self._movement_start_time is None
            or self._movement_start_position is None
            or self._target_position is None
        ):
            return

        elapsed = monotonic() - self._movement_start_time
        travel_time = (
            self._travel_time_up if self._movement_direction > 0 else self._travel_time_down
        )
        self._current_position = position_after(
            self._movement_start_position,
            self._movement_direction,
            elapsed,
            travel_time,
            self._target_position,
        )

        if self._current_position == self._target_position:
            self._finalize_position(self._target_position)

    @callback
    def _stop_estimated_motion(self) -> None:
        """Arrêter le mouvement estimé à la position courante."""
        self._cancel_motion_callbacks()
        self._movement_direction = 0
        self._movement_start_time = None
        self._movement_start_position = None
        self._target_position = None
        self.async_write_ha_state()

    @callback
    def _finalize_position(self, position: int) -> None:
        """Clore un mouvement estimé sur une position cible."""
        self._current_position = clamp_position(position)
        self._stop_estimated_motion()

    @callback
    def _schedule_target_reached(self) -> None:
        """Programmer la fin logique du mouvement et un STOP si besoin."""
        assert self._current_position is not None
        assert self._target_position is not None

        distance = abs(self._target_position - self._current_position)
        travel_time = (
            self._travel_time_up if self._movement_direction > 0 else self._travel_time_down
        )
        duration = travel_duration(distance, travel_time)

        if duration <= 0:
            self._finalize_position(self._target_position)
            return

        if self._target_position in (0, 100):
            self._target_reached_unsub = async_call_later(
                self.hass, duration, self._handle_target_reached
            )
            return

        self._target_reached_unsub = async_call_later(
            self.hass, duration, self._handle_partial_target_reached
        )

    @callback
    def _schedule_progress_tick(self) -> None:
        """Programmer une mise à jour visuelle périodique de la position."""
        if self._movement_direction == 0:
            return
        self._progress_unsub = async_call_later(self.hass, 1, self._handle_progress_tick)

    @callback
    def _handle_progress_tick(self, _now: Any) -> None:
        """Rafraîchir l'état pendant le mouvement."""
        self._progress_unsub = None
        self._refresh_position()
        self.async_write_ha_state()
        if self._movement_direction != 0:
            self._schedule_progress_tick()

    @callback
    def _handle_target_reached(self, _now: Any) -> None:
        """Clore un mouvement jusqu'en butée sans envoyer STOP."""
        self._target_reached_unsub = None
        if self._target_position is not None:
            self._finalize_position(self._target_position)

    @callback
    def _handle_partial_target_reached(self, _now: Any) -> None:
        """Envoyer STOP au bon moment pour un déplacement partiel."""
        self._target_reached_unsub = None
        self.hass.async_create_task(self._async_complete_partial_move())

    async def _async_complete_partial_move(self) -> None:
        """Terminer un déplacement partiel avec une commande STOP."""
        target_position = self._target_position
        await self._async_transmit(BUTTON_STOP, DEFAULT_CHECK_STOP)
        if target_position is not None:
            self._finalize_position(target_position)

    @callback
    def _cancel_motion_callbacks(self) -> None:
        """Annuler les timers actifs liés au mouvement estimé."""
        if self._target_reached_unsub is not None:
            self._target_reached_unsub()
            self._target_reached_unsub = None
        if self._progress_unsub is not None:
            self._progress_unsub()
            self._progress_unsub = None
