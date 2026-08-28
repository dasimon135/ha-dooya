"""Config flow pour l'intégration Dooya RF Covers."""

from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
import voluptuous as vol

from .const import (
    CONF_CHANNEL,
    CONF_CHECK,
    CONF_COVER_NAME,
    CONF_DOOYA_ID,
    CONF_ESPHOME_DEVICE,
    CONF_FAVORITE_POSITION,
    CONF_REPEAT_COUNT,
    CONF_TRAVEL_TIME_DOWN,
    CONF_TRAVEL_TIME_UP,
    DEFAULT_CHANNEL,
    DEFAULT_REPEAT_COUNT,
    DEFAULT_TRAVEL_TIME_DOWN,
    DEFAULT_TRAVEL_TIME_UP,
    DOMAIN,
    EVENT_DOOYA_RECEIVED,
    MAX_CHANNEL,
    TRANSMIT_SERVICE_SUFFIX,
    entry_value,
)
from .dooya_protocol import BUTTON_UP, MAX_DOOYA_ID, DooyaData, check_for_button

# Maximum time spent listening for a remote in learn mode (seconds)
LEARN_TIMEOUT_SEC = 30


def _parse_dooya_id(raw: str) -> int:
    """Parse a hexadecimal remote id, rejecting anything wider than 24 bits.

    The id field of a Dooya frame is 24 bits: a wider value would be silently
    truncated by the encoder on the ESP32 and the node would transmit a
    different remote id than the one shown in the UI.
    """
    value = int(raw, 16)
    if not 0 <= value <= MAX_DOOYA_ID:
        raise ValueError(f"dooya id {value:X} does not fit in 24 bits")
    return value


def shutter_unique_id(dooya_id: int, channel: int) -> str:
    """Return the unique id identifying one physical shutter.

    Keyed on id + channel, not id alone: the broadcast channel 0 legitimately
    coexists with the per-channel entries of the same remote.
    """
    return f"{dooya_id:06X}_{channel}"


def _list_transmit_devices(hass) -> list[str]:
    """List ESPHome devices exposing a transmit_dooya service."""
    esphome_services = hass.services.async_services().get("esphome", {})
    devices = []
    for service_name in esphome_services:
        if service_name.endswith(TRANSMIT_SERVICE_SUFFIX):
            devices.append(
                service_name[: -len(TRANSMIT_SERVICE_SUFFIX)].replace("_", "-")
            )
    return sorted(devices)


class DooyaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow pour ajouter un volet Dooya."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> DooyaOptionsFlow:
        """Retourner le flow d'options pour une entrée existante."""
        return DooyaOptionsFlow(config_entry)

    def __init__(self) -> None:
        """Initialiser le config flow."""
        self._learned_data: DooyaData | None = None
        self._esphome_device: str = ""
        self._learn_task: asyncio.Task[DooyaData | None] | None = None

    def _available_esphome_devices(self) -> list[str]:
        """Lister les devices ESPHome exposant un service transmit_dooya."""
        return _list_transmit_devices(self.hass)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
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
    ) -> ConfigFlowResult:
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
    ) -> ConfigFlowResult:
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
    ) -> ConfigFlowResult:
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

            # Completing the task is enough: the flow manager watches the
            # progress_task passed to async_show_progress and advances the
            # flow itself when it finishes.
            event_received.set()

        unsubscribe = self.hass.bus.async_listen(EVENT_DOOYA_RECEIVED, _handle_event)

        try:
            await asyncio.wait_for(event_received.wait(), timeout=LEARN_TIMEOUT_SEC)
        except TimeoutError:
            return None
        finally:
            unsubscribe()

        return result

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Étape 3 : confirmer les données apprises et nommer le volet."""
        assert self._learned_data is not None

        if user_input is not None:
            return await self._async_create_entry(
                name=user_input[CONF_COVER_NAME],
                dooya_id=self._learned_data.id,
                channel=self._learned_data.channel,
                check=self._learned_data.check,
                travel_time_up=user_input[CONF_TRAVEL_TIME_UP],
                travel_time_down=user_input[CONF_TRAVEL_TIME_DOWN],
            )

        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_COVER_NAME): str,
                    vol.Required(
                        CONF_TRAVEL_TIME_UP,
                        default=DEFAULT_TRAVEL_TIME_UP,
                    ): vol.All(vol.Coerce(float), vol.Range(min=1, max=240)),
                    vol.Required(
                        CONF_TRAVEL_TIME_DOWN,
                        default=DEFAULT_TRAVEL_TIME_DOWN,
                    ): vol.All(vol.Coerce(float), vol.Range(min=1, max=240)),
                }
            ),
            description_placeholders={
                "dooya_id": f"0x{self._learned_data.id:06X}",
                "channel": str(self._learned_data.channel),
            },
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 3b: manual entry of the Dooya id."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                dooya_id = _parse_dooya_id(user_input[CONF_DOOYA_ID])
            except ValueError:
                errors[CONF_DOOYA_ID] = "invalid_dooya_id"
            else:
                return await self._async_create_entry(
                    name=user_input[CONF_COVER_NAME],
                    dooya_id=dooya_id,
                    channel=user_input[CONF_CHANNEL],
                    # The check nibble is derived from the button at transmit
                    # time; record the UP value for reference only.
                    check=check_for_button(BUTTON_UP),
                    travel_time_up=user_input[CONF_TRAVEL_TIME_UP],
                    travel_time_down=user_input[CONF_TRAVEL_TIME_DOWN],
                )

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_COVER_NAME): str,
                    vol.Required(CONF_DOOYA_ID): str,
                    vol.Required(CONF_CHANNEL, default=DEFAULT_CHANNEL): vol.All(
                        int, vol.Range(min=0, max=MAX_CHANNEL)
                    ),
                    vol.Required(
                        CONF_TRAVEL_TIME_UP,
                        default=DEFAULT_TRAVEL_TIME_UP,
                    ): vol.All(vol.Coerce(float), vol.Range(min=1, max=240)),
                    vol.Required(
                        CONF_TRAVEL_TIME_DOWN,
                        default=DEFAULT_TRAVEL_TIME_DOWN,
                    ): vol.All(vol.Coerce(float), vol.Range(min=1, max=240)),
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Fix the identity of an existing shutter without recreating it.

        Lets the user correct dooya_id, channel or the cover name; the entry
        reloads with the updated data.
        """
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                dooya_id = _parse_dooya_id(user_input[CONF_DOOYA_ID])
            except ValueError:
                errors[CONF_DOOYA_ID] = "invalid_dooya_id"
            else:
                channel = user_input[CONF_CHANNEL]
                # Editing an entry into an identity another entry already owns
                # would create the same duplicate the user step guards against.
                if self._conflicting_entry(
                    dooya_id, channel, ignore_entry_id=entry.entry_id
                ):
                    errors[CONF_DOOYA_ID] = "duplicate_shutter"
                else:
                    name = user_input[CONF_COVER_NAME]
                    return self.async_update_reload_and_abort(
                        entry,
                        title=name,
                        unique_id=shutter_unique_id(dooya_id, channel),
                        data_updates={
                            CONF_DOOYA_ID: dooya_id,
                            CONF_CHANNEL: channel,
                            CONF_COVER_NAME: name,
                        },
                    )

        data = entry.data
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_COVER_NAME, default=data.get(CONF_COVER_NAME, "")
                    ): str,
                    vol.Required(
                        CONF_DOOYA_ID,
                        default=f"{data.get(CONF_DOOYA_ID, 0):06X}",
                    ): str,
                    vol.Required(
                        CONF_CHANNEL, default=data.get(CONF_CHANNEL, DEFAULT_CHANNEL)
                    ): vol.All(int, vol.Range(min=0, max=MAX_CHANNEL)),
                }
            ),
            errors=errors,
        )

    @callback
    def _conflicting_entry(
        self, dooya_id: int, channel: int, *, ignore_entry_id: str | None = None
    ) -> ConfigEntry | None:
        """Return an existing entry already driving this shutter, if any.

        Matches on the entry data rather than on the unique id so that entries
        created before unique ids were introduced are caught too.
        """
        for entry in self._async_current_entries():
            if entry.entry_id == ignore_entry_id:
                continue
            if (
                entry.data.get(CONF_DOOYA_ID) == dooya_id
                and entry.data.get(CONF_CHANNEL) == channel
            ):
                return entry
        return None

    async def _async_create_entry(
        self,
        name: str,
        dooya_id: int,
        channel: int,
        check: int,
        travel_time_up: float,
        travel_time_down: float,
    ) -> ConfigFlowResult:
        """Create the config entry, refusing to drive the same shutter twice.

        Two entries for one shutter would each run their own position estimate
        and would each see the other's transmissions as a physical remote
        press, so the two estimates would drift apart permanently.
        """
        if self._conflicting_entry(dooya_id, channel) is not None:
            return self.async_abort(reason="already_configured")

        await self.async_set_unique_id(shutter_unique_id(dooya_id, channel))
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=name,
            data={
                CONF_ESPHOME_DEVICE: self._esphome_device,
                CONF_DOOYA_ID: dooya_id,
                CONF_CHANNEL: channel,
                CONF_CHECK: check,
                CONF_COVER_NAME: name,
                CONF_TRAVEL_TIME_UP: travel_time_up,
                CONF_TRAVEL_TIME_DOWN: travel_time_down,
            },
        )


class DooyaOptionsFlow(OptionsFlow):
    """Options flow pour ajuster les temps de trajet d'un volet Dooya."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialiser le flow d'options."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Modifier les temps de trajet estimés."""
        entry = self._config_entry
        current_device = entry_value(entry, CONF_ESPHOME_DEVICE, "")
        current_up = entry_value(entry, CONF_TRAVEL_TIME_UP, DEFAULT_TRAVEL_TIME_UP)
        current_down = entry_value(
            entry, CONF_TRAVEL_TIME_DOWN, DEFAULT_TRAVEL_TIME_DOWN
        )
        current_repeat = int(
            entry_value(entry, CONF_REPEAT_COUNT, DEFAULT_REPEAT_COUNT)
        )

        if user_input is not None:
            return self.async_create_entry(data=user_input)

        # With several TX+RX nodes in the house, a cover can be reassigned to
        # the nearest node here without re-creating the entry. Keep the
        # current device selectable even if its node is offline right now.
        devices = _list_transmit_devices(self.hass)
        if current_device and current_device not in devices:
            devices = sorted([*devices, current_device])

        schema: dict[Any, Any] = {}
        if devices:
            schema[
                vol.Required(CONF_ESPHOME_DEVICE, default=current_device)
            ] = vol.In(devices)

        favorite_field = (
            vol.Optional(
                CONF_FAVORITE_POSITION,
                description={
                    "suggested_value": self._config_entry.options.get(
                        CONF_FAVORITE_POSITION
                    )
                },
            )
            if self._config_entry.options.get(CONF_FAVORITE_POSITION) is not None
            else vol.Optional(CONF_FAVORITE_POSITION)
        )

        schema.update(
            {
                vol.Required(
                    CONF_TRAVEL_TIME_UP,
                    default=current_up,
                ): vol.All(vol.Coerce(float), vol.Range(min=1, max=240)),
                vol.Required(
                    CONF_TRAVEL_TIME_DOWN,
                    default=current_down,
                ): vol.All(vol.Coerce(float), vol.Range(min=1, max=240)),
                vol.Required(
                    CONF_REPEAT_COUNT,
                    default=current_repeat,
                ): vol.All(int, vol.Range(min=1, max=3)),
                favorite_field: vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema),
        )
