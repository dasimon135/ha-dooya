"""Config flow pour l'intégration Dooya RF Covers."""

from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow
from homeassistant.data_entry_flow import FlowResult
from homeassistant.core import callback

from .const import (
    CONF_CHANNEL,
    CONF_CHECK,
    CONF_COVER_NAME,
    CONF_DOOYA_ID,
    CONF_ESPHOME_DEVICE,
    DEFAULT_CHANNEL,
    DOMAIN,
)
from .dooya_protocol import DooyaData

# Événement ESPHome publié lors de la réception d'une trame Dooya
DOOYA_LEARN_EVENT = "esphome.dooya_received"
# Délai maximum d'attente en mode apprentissage (secondes)
LEARN_TIMEOUT_SEC = 30


class DooyaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow pour ajouter un volet Dooya."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialiser le config flow."""
        self._learned_data: DooyaData | None = None
        self._esphome_device: str = ""
        self._learn_task: asyncio.Task[DooyaData | None] | None = None

    def _available_esphome_devices(self) -> list[str]:
        """Lister les devices ESPHome exposant un service transmit_dooya."""
        esphome_services = self.hass.services.async_services().get("esphome", {})
        devices = []
        suffix = "_transmit_dooya"
        for service_name in esphome_services:
            if service_name.endswith(suffix):
                devices.append(service_name[: -len(suffix)].replace("_", "-"))
        return sorted(devices)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Étape 1 : entrer le nom du device ESPHome transmetteur."""
        errors: dict[str, str] = {}
        available_devices = self._available_esphome_devices()
        default_device = available_devices[0] if len(available_devices) == 1 else ""

        if user_input is not None:
            selected_device = user_input.get(CONF_ESPHOME_DEVICE, "").strip()
            if not selected_device and len(available_devices) == 1:
                selected_device = available_devices[0]

            if not selected_device:
                if len(available_devices) > 1:
                    errors[CONF_ESPHOME_DEVICE] = "required_esphome_device"
                else:
                    errors[CONF_ESPHOME_DEVICE] = "unknown_esphome_device"
            elif selected_device not in available_devices:
                errors[CONF_ESPHOME_DEVICE] = "unknown_esphome_device"
            else:
                self._esphome_device = selected_device
                return await self.async_step_method()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_ESPHOME_DEVICE, default=default_device): str,
                }
            ),
            description_placeholders={
                "example": "volets-dooya-rf433",
                "detected": ", ".join(available_devices) if available_devices else "aucun",
            },
            errors=errors,
        )

    async def async_step_method(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Étape 2 : choisir entre apprentissage automatique et saisie manuelle."""
        if user_input is not None:
            if user_input["method"] == "manual":
                return await self.async_step_manual()
            return await self.async_step_learn()

        return self.async_show_form(
            step_id="method",
            data_schema=vol.Schema(
                {
                    vol.Required("method", default="manual"): vol.In(
                        {
                            "manual": "manual",
                            "learn": "learn",
                        }
                    ),
                }
            ),
        )

    async def async_step_learn(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Étape 3a : lancer immédiatement l'apprentissage automatique."""
        if self._learn_task is None:
            self._learn_task = self.hass.async_create_task(
                self._async_wait_for_dooya_signal()
            )

        if not self._learn_task.done():
            return self.async_show_progress(
                step_id="learn",
                progress_action="listen_remote",
                progress_task=self._learn_task,
                description_placeholders={"timeout": str(LEARN_TIMEOUT_SEC)},
            )

        learned = self._learn_task.result()
        self._learn_task = None

        if learned is None:
            return await self.async_step_learn_retry()

        self._learned_data = learned
        return self.async_show_progress_done(next_step_id="confirm")

    async def async_step_learn_retry(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Proposer un nouvel essai ou une saisie manuelle après timeout."""
        if user_input is not None:
            if user_input.get("skip"):
                return await self.async_step_manual()
            return await self.async_step_learn()

        return self.async_show_form(
            step_id="learn_retry",
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
                    id=int(data["id"], 16)
                    if isinstance(data["id"], str)
                    else int(data["id"]),
                    channel=int(data["channel"]),
                    button=int(data["button"]),
                    check=int(data["check"]),
                )
            except (KeyError, ValueError, TypeError):
                return

            event_received.set()
            self.hass.async_create_task(self.hass.config_entries.flow.async_configure(self.flow_id))

        unsubscribe = self.hass.bus.async_listen(DOOYA_LEARN_EVENT, _handle_event)

        try:
            await asyncio.wait_for(event_received.wait(), timeout=LEARN_TIMEOUT_SEC)
        except asyncio.TimeoutError:
            return None
        finally:
            unsubscribe()

        return result

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Étape 3 : confirmer les données apprises et nommer le volet."""
        assert self._learned_data is not None

        if user_input is not None:
            return self._create_entry(
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
    ) -> FlowResult:
        """Étape 3b : saisie manuelle de l'ID Dooya."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                dooya_id = int(user_input[CONF_DOOYA_ID], 16)
            except ValueError:
                errors[CONF_DOOYA_ID] = "invalid_dooya_id"
            else:
                return self._create_entry(
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
    def _create_entry(
        self,
        name: str,
        dooya_id: int,
        channel: int,
        check: int,
    ) -> FlowResult:
        """Créer l'entrée de configuration."""
        return self.async_create_entry(
            title=name,
            data={
                CONF_ESPHOME_DEVICE: self._esphome_device,
                CONF_DOOYA_ID: dooya_id,
                CONF_CHANNEL: channel,
                CONF_CHECK: check,
                CONF_COVER_NAME: name,
            },
        )
