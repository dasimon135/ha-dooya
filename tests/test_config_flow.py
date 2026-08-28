"""Tests for the Dooya config flow (requires the HA test harness).

Skipped automatically when pytest-homeassistant-custom-component is not
installed (e.g. on Windows, where the harness cannot run).
"""

from __future__ import annotations

import sys

import pytest

if sys.platform == "win32":
    pytest.skip(
        "the Home Assistant test harness does not run on Windows",
        allow_module_level=True,
    )
pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dooya.const import (
    CONF_CHANNEL,
    CONF_CHECK,
    CONF_COVER_NAME,
    CONF_DOOYA_ID,
    CONF_ESPHOME_DEVICE,
    CONF_TRAVEL_TIME_DOWN,
    CONF_TRAVEL_TIME_UP,
    DOMAIN,
)

GATEWAY_SLUG = "volets-dooya-rf433"
GATEWAY_SERVICE = "volets_dooya_rf433_transmit_dooya"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Make custom_components/ visible to the test hass instance."""
    return


@pytest.fixture
def gateway_service(hass: HomeAssistant) -> list[dict]:
    """Register a fake ESPHome transmit service and record its calls."""
    calls: list[dict] = []

    @callback
    def _record(call) -> None:
        calls.append(dict(call.data))

    hass.services.async_register("esphome", GATEWAY_SERVICE, _record)
    return calls


async def test_user_flow_manual_happy_path(
    hass: HomeAssistant, gateway_service: list[dict]
) -> None:
    """Full user flow with manual entry creates a config entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ESPHOME_DEVICE: GATEWAY_SLUG}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "method"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"method": "manual"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "manual"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_COVER_NAME: "Salon",
            CONF_DOOYA_ID: "00D1C917",
            CONF_CHANNEL: 5,
            CONF_TRAVEL_TIME_UP: 20.0,
            CONF_TRAVEL_TIME_DOWN: 18.0,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Salon"
    assert result["data"] == {
        CONF_ESPHOME_DEVICE: GATEWAY_SLUG,
        CONF_DOOYA_ID: 0x00D1C917,
        CONF_CHANNEL: 5,
        CONF_CHECK: 1,
        CONF_COVER_NAME: "Salon",
        CONF_TRAVEL_TIME_UP: 20.0,
        CONF_TRAVEL_TIME_DOWN: 18.0,
    }


async def test_user_step_lists_the_detected_devices(
    hass: HomeAssistant, gateway_service: list[dict]
) -> None:
    """The first step names the nodes it found, so the user can copy one."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["description_placeholders"]["detected"] == GATEWAY_SLUG


async def test_user_step_placeholder_stays_locale_neutral(
    hass: HomeAssistant,
) -> None:
    """With no node found, the placeholder must not carry a word.

    It is interpolated into a sentence Home Assistant has already translated,
    so any word here is wrong in every language but its own — a hardcoded
    French "aucun" used to be shown to English users. Asserting that the value
    contains no letters is what actually pins the invariant: a future
    translated word cannot slip back in unnoticed.
    """
    # No `gateway_service` fixture: nothing exposes a transmit_dooya action.
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    detected = result["description_placeholders"]["detected"]
    assert detected == "0"
    assert not any(char.isalpha() for char in detected)


async def test_user_step_rejects_unknown_device(
    hass: HomeAssistant, gateway_service: list[dict]
) -> None:
    """An ESPHome device without a transmit service is rejected."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ESPHOME_DEVICE: "does-not-exist"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {CONF_ESPHOME_DEVICE: "unknown_esphome_device"}


async def test_manual_step_rejects_invalid_dooya_id(
    hass: HomeAssistant, gateway_service: list[dict]
) -> None:
    """A non-hexadecimal identifier shows an error on the manual step."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ESPHOME_DEVICE: GATEWAY_SLUG}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"method": "manual"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_COVER_NAME: "Salon",
            CONF_DOOYA_ID: "NOT-HEX",
            CONF_CHANNEL: 5,
            CONF_TRAVEL_TIME_UP: 20.0,
            CONF_TRAVEL_TIME_DOWN: 18.0,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "manual"
    assert result["errors"] == {CONF_DOOYA_ID: "invalid_dooya_id"}


async def test_reconfigure_updates_entry(
    hass: HomeAssistant, gateway_service: list[dict]
) -> None:
    """The reconfigure step fixes the shutter identity in place."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Salon",
        data={
            CONF_ESPHOME_DEVICE: GATEWAY_SLUG,
            CONF_DOOYA_ID: 0x00D1C917,
            CONF_CHANNEL: 5,
            CONF_CHECK: 1,
            CONF_COVER_NAME: "Salon",
            CONF_TRAVEL_TIME_UP: 20.0,
            CONF_TRAVEL_TIME_DOWN: 18.0,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_COVER_NAME: "Salon gauche",
            CONF_DOOYA_ID: "ABCDEF",
            CONF_CHANNEL: 7,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.title == "Salon gauche"
    assert entry.data[CONF_DOOYA_ID] == 0xABCDEF
    assert entry.data[CONF_CHANNEL] == 7
    assert entry.data[CONF_COVER_NAME] == "Salon gauche"
    # Travel times are untouched by a reconfigure.
    assert entry.data[CONF_TRAVEL_TIME_UP] == 20.0

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_manual_step_rejects_oversized_dooya_id(
    hass: HomeAssistant, gateway_service: list[dict]
) -> None:
    """An id wider than 24 bits is rejected instead of being truncated."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ESPHOME_DEVICE: GATEWAY_SLUG}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"method": "manual"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_COVER_NAME: "Salon",
            CONF_DOOYA_ID: "FFFFFFFFFF",  # 40 bits
            CONF_CHANNEL: 5,
            CONF_TRAVEL_TIME_UP: 20.0,
            CONF_TRAVEL_TIME_DOWN: 18.0,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_DOOYA_ID: "invalid_dooya_id"}


async def _run_manual_flow(
    hass: HomeAssistant, dooya_id: str, channel: int, name: str
) -> dict:
    """Drive the manual flow to completion and return the final result."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ESPHOME_DEVICE: GATEWAY_SLUG}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"method": "manual"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_COVER_NAME: name,
            CONF_DOOYA_ID: dooya_id,
            CONF_CHANNEL: channel,
            CONF_TRAVEL_TIME_UP: 20.0,
            CONF_TRAVEL_TIME_DOWN: 18.0,
        },
    )
    await hass.async_block_till_done()
    return result


async def test_same_shutter_cannot_be_added_twice(
    hass: HomeAssistant, gateway_service: list[dict]
) -> None:
    """Two entries for one shutter would fight over the position estimate."""
    first = await _run_manual_flow(hass, "D1C917", 5, "Salon")
    assert first["type"] is FlowResultType.CREATE_ENTRY

    second = await _run_manual_flow(hass, "D1C917", 5, "Salon (doublon)")
    assert second["type"] is FlowResultType.ABORT
    assert second["reason"] == "already_configured"


async def test_broadcast_channel_coexists_with_per_channel_entry(
    hass: HomeAssistant, gateway_service: list[dict]
) -> None:
    """Channel 0 is a different shutter identity, not a duplicate."""
    first = await _run_manual_flow(hass, "D1C917", 5, "Salon")
    assert first["type"] is FlowResultType.CREATE_ENTRY

    broadcast = await _run_manual_flow(hass, "D1C917", 0, "Tous les volets")
    assert broadcast["type"] is FlowResultType.CREATE_ENTRY


async def test_reconfigure_refuses_to_collide_with_another_entry(
    hass: HomeAssistant, gateway_service: list[dict]
) -> None:
    """Editing an entry onto another entry's identity is refused."""
    assert (await _run_manual_flow(hass, "D1C917", 5, "Salon"))[
        "type"
    ] is FlowResultType.CREATE_ENTRY
    assert (await _run_manual_flow(hass, "D1C917", 6, "Cuisine"))[
        "type"
    ] is FlowResultType.CREATE_ENTRY

    cuisine = next(
        e for e in hass.config_entries.async_entries(DOMAIN) if e.title == "Cuisine"
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": cuisine.entry_id,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_COVER_NAME: "Cuisine", CONF_DOOYA_ID: "D1C917", CONF_CHANNEL: 5},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_DOOYA_ID: "duplicate_shutter"}
    # The entry is untouched.
    assert cuisine.data[CONF_CHANNEL] == 6


async def test_reconfigure_keeping_own_identity_is_allowed(
    hass: HomeAssistant, gateway_service: list[dict]
) -> None:
    """Renaming without changing id/channel must not self-collide."""
    assert (await _run_manual_flow(hass, "D1C917", 5, "Salon"))[
        "type"
    ] is FlowResultType.CREATE_ENTRY
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_COVER_NAME: "Salon gauche", CONF_DOOYA_ID: "D1C917", CONF_CHANNEL: 5},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_COVER_NAME] == "Salon gauche"


async def test_manual_step_accepts_channel_above_16(
    hass: HomeAssistant, gateway_service: list[dict]
) -> None:
    """Channels above 16 are legal: the frame carries the channel on 8 bits.

    Reported in issue #18 by a user whose remotes start at channel 81.
    """
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ESPHOME_DEVICE: GATEWAY_SLUG}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"method": "manual"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_COVER_NAME: "Chambre",
            CONF_DOOYA_ID: "00D1C917",
            CONF_CHANNEL: 81,
            CONF_TRAVEL_TIME_UP: 20.0,
            CONF_TRAVEL_TIME_DOWN: 18.0,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_CHANNEL] == 81


@pytest.mark.parametrize("channel", [0, 255])
async def test_manual_step_accepts_full_8_bit_channel_range(
    hass: HomeAssistant, gateway_service: list[dict], channel: int
) -> None:
    """Both ends of the 8-bit field are valid: 0 is broadcast, 255 is the max."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ESPHOME_DEVICE: GATEWAY_SLUG}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"method": "manual"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_COVER_NAME: f"Volet {channel}",
            CONF_DOOYA_ID: "00D1C917",
            CONF_CHANNEL: channel,
            CONF_TRAVEL_TIME_UP: 20.0,
            CONF_TRAVEL_TIME_DOWN: 18.0,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_CHANNEL] == channel


async def test_manual_step_rejects_channel_above_255(
    hass: HomeAssistant, gateway_service: list[dict]
) -> None:
    """A channel wider than the 8-bit field cannot be transmitted."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ESPHOME_DEVICE: GATEWAY_SLUG}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"method": "manual"}
    )

    with pytest.raises(InvalidData):
        await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_COVER_NAME: "Trop haut",
                CONF_DOOYA_ID: "00D1C917",
                CONF_CHANNEL: 256,
                CONF_TRAVEL_TIME_UP: 20.0,
                CONF_TRAVEL_TIME_DOWN: 18.0,
            },
        )


async def test_reconfigure_accepts_channel_above_16(
    hass: HomeAssistant, gateway_service: list[dict]
) -> None:
    """Reconfiguring onto a channel above 16 must work too (issue #18)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Chambre",
        data={
            CONF_ESPHOME_DEVICE: GATEWAY_SLUG,
            CONF_DOOYA_ID: 0x00D1C917,
            CONF_CHANNEL: 5,
            CONF_CHECK: 1,
            CONF_COVER_NAME: "Chambre",
            CONF_TRAVEL_TIME_UP: 20.0,
            CONF_TRAVEL_TIME_DOWN: 18.0,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_COVER_NAME: "Chambre",
            CONF_DOOYA_ID: "00D1C917",
            CONF_CHANNEL: 200,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_CHANNEL] == 200

    assert await hass.config_entries.async_unload(entry.entry_id)
