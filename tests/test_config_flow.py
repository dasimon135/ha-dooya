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
from homeassistant.data_entry_flow import FlowResultType
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
            CONF_CHECK: 1,
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
            CONF_CHECK: 1,
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
            CONF_DOOYA_ID: "00ABCDEF",
            CONF_CHANNEL: 7,
            CONF_CHECK: 2,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.title == "Salon gauche"
    assert entry.data[CONF_DOOYA_ID] == 0x00ABCDEF
    assert entry.data[CONF_CHANNEL] == 7
    assert entry.data[CONF_CHECK] == 2
    assert entry.data[CONF_COVER_NAME] == "Salon gauche"
    # Travel times are untouched by a reconfigure.
    assert entry.data[CONF_TRAVEL_TIME_UP] == 20.0

    assert await hass.config_entries.async_unload(entry.entry_id)
