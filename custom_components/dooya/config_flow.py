"""Config flow pour l'intégration Dooya RF Covers."""

from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol

from homeassistant.components.radio_frequency import async_get_transmitters
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er, selector

from .const import (
    CONF_CHANNEL,
    CONF_CHECK,
    CONF_COVER_NAME,
    CONF_DOOYA_ID,
    CONF_TRANSMITTER,
    DEFAULT_CHANNEL,
    DOMAIN,
)
from .dooya_protocol import BUTTON_UP, DOOYA_FREQUENCY_HZ, DooyaData, decode_dooya

# Événement ESPHome publié lors de la réception d'une trame Dooya
DOOYA_LEARN_EVENT = "esphome.dooya_received"
# Délai maximum d'attente en mode apprentissage (secondes)
LEARN_TIMEOUT_SEC = 30


class DooyaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow pour ajouter un volet Dooya."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialiser le config flow."""
        self._transmitter_uuid: str | None = None
        self._learned_data: DooyaData | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Étape 1 : choisir le transmetteur RF compatible Dooya."""
        errors: dict[str, str] = {}

        # Construire une commande factice pour filtrer les transmetteurs compatibles
        # (433.92 MHz OOK — filtre automatique via async_get_transmitters)
        try:
            from homeassistant.components.radio_frequency import ModulationType

            transmitters = async_get_transmitters(
                self.hass,
                DOOYA_FREQUENCY_HZ,
                ModulationType.OOK,
            )
        except (HomeAssistantError, ImportError):
            transmitters = []

        if not transmitters:
            return self.async_abort(reason="no_transmitters")

        if user_input is not None:
            registry = er.async_get(self.hass)
            entity_entry = registry.async_get(user_input[CONF_TRANSMITTER])
            if entity_entry is not None:
                self._transmitter_uuid = entity_entry.id
                return await self.async_step_learn()
            errors[CONF_TRANSMITTER] = "invalid_transmitter"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TRANSMITTER): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            include_entities=transmitters,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_learn(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Étape 2 : mode apprentissage — appuyer sur UP de la télécommande."""
        if user_input is not None:
            if user_input.get("skip"):
                # L'utilisateur veut saisir manuellement
                return await self.async_step_manual()

        # Attendre un événement ESPHome dooya_received
        learned = await self._async_wait_for_dooya_signal()

        if learned is not None:
            self._learned_data = learned
            return await self.async_step_confirm()

        # Timeout ou pas d'événement reçu → proposer saisie manuelle
        return self.async_show_form(
            step_id="learn",
            data_schema=vol.Schema(
                {
                    vol.Optional("skip", default=False): bool,
                }
            ),
            description_placeholders={"timeout": str(LEARN_TIMEOUT_SEC)},
            errors={"base": "learn_timeout"},
        )

    async def _async_wait_for_dooya_signal(self) -> DooyaData | None:
        """Écouter l'événement HA publié par ESPHome lors d'une réception Dooya."""
        result: DooyaData | None = None
        event_received = asyncio.Event()

        @callback
        def _handle_event(event: Any) -> None:
            nonlocal result
            data = event.data
            try:
                result = DooyaData(
                    id=int(data["id"], 16) if isinstance(data["id"], str) else int(data["id"]),
                    channel=int(data["channel"]),
                    button=int(data["button"]),
                    check=int(data["check"]),
                )
            except (KeyError, ValueError):
                return
            # On ne garde que les pressions sur UP pour l'apprentissage
            if result.button == BUTTON_UP:
                event_received.set()

        unsubscribe = self.hass.bus.async_listen(DOOYA_LEARN_EVENT, _handle_event)
        try:
            await asyncio.wait_for(event_received.wait(), timeout=LEARN_TIMEOUT_SEC)
        except asyncio.TimeoutError:
            result = None
        finally:
            unsubscribe()

        return result

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Étape 3 : confirmer les données apprises et nommer le volet."""
        assert self._learned_data is not None

        if user_input is not None:
            return self._async_create_entry(
                name=user_input[CONF_COVER_NAME],
                dooya_id=self._learned_data.id,
                channel=self._learned_data.channel,
                check=self._learned_data.check,
            )

        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_COVER_NAME): str,
                }
            ),
            description_placeholders={
                "dooya_id": f"0x{self._learned_data.id:08X}",
                "channel": str(self._learned_data.channel),
            },
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Étape alternative : saisie manuelle de l'ID Dooya."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                dooya_id = int(user_input[CONF_DOOYA_ID], 16)
            except ValueError:
                errors[CONF_DOOYA_ID] = "invalid_dooya_id"
            else:
                return self._async_create_entry(
                    name=user_input[CONF_COVER_NAME],
                    dooya_id=dooya_id,
                    channel=user_input[CONF_CHANNEL],
                    check=user_input[CONF_CHECK],
                )

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_COVER_NAME): str,
                    vol.Required(CONF_DOOYA_ID): str,
                    vol.Required(CONF_CHANNEL, default=DEFAULT_CHANNEL): vol.All(
                        int, vol.Range(min=1, max=16)
                    ),
                    vol.Required(CONF_CHECK, default=1): vol.All(
                        int, vol.Range(min=0, max=15)
                    ),
                }
            ),
            errors=errors,
        )

    @callback
    def _async_create_entry(
        self,
        name: str,
        dooya_id: int,
        channel: int,
        check: int,
    ) -> ConfigFlowResult:
        """Créer l'entrée de configuration."""
        return self.async_create_entry(
            title=name,
            data={
                CONF_TRANSMITTER: self._transmitter_uuid,
                CONF_DOOYA_ID: dooya_id,
                CONF_CHANNEL: channel,
                CONF_CHECK: check,
                CONF_COVER_NAME: name,
            },
        )
