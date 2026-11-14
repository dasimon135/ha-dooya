"""Tests for the position confidence sensor.

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

from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache,
)

from custom_components.dooya_rf.const import (
    CONF_CHANNEL,
    CONF_CHECK,
    CONF_COVER_NAME,
    CONF_DOOYA_ID,
    CONF_ESPHOME_DEVICE,
    CONF_IS_GROUP,
    CONF_TRAVEL_TIME_DOWN,
    CONF_TRAVEL_TIME_UP,
    DOMAIN,
)

GATEWAY_SERVICE = "volets_dooya_rf433_transmit_dooya"
COVER_ID = "cover.salon"
SENSOR_ID = "sensor.salon_position_confidence"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Make custom_components/ visible to the test hass instance."""
    return


@pytest.fixture(autouse=True)
def gateway(hass: HomeAssistant) -> None:
    """Register the gateway's transmit action, so commands can go out."""

    @callback
    def _record(call) -> None:
        return

    hass.services.async_register("esphome", GATEWAY_SERVICE, _record)


async def _setup(
    hass: HomeAssistant, name: str = "Salon", channel: int = 5, group: bool = False
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=name,
        data={
            CONF_ESPHOME_DEVICE: "volets-dooya-rf433",
            CONF_DOOYA_ID: 0xC2D604,
            CONF_CHANNEL: channel,
            CONF_CHECK: 1,
            CONF_COVER_NAME: name,
            CONF_TRAVEL_TIME_UP: 3.0,
            CONF_TRAVEL_TIME_DOWN: 3.0,
        },
        options={CONF_IS_GROUP: True} if group else {},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_a_synced_cover_is_trusted(hass: HomeAssistant) -> None:
    await _setup(hass)
    state = hass.states.get(SENSOR_ID)
    assert state.state == "high"
    assert state.attributes["options"] == ["high", "medium", "low"]
    assert state.attributes["device_class"] == "enum"


async def test_the_sensor_is_a_diagnostic(hass: HomeAssistant) -> None:
    await _setup(hass)
    assert er.async_get(hass).async_get(SENSOR_ID).entity_category == "diagnostic"


@pytest.mark.parametrize(("moves", "level"), [(4, "high"), (5, "medium"), (10, "low")])
async def test_the_sensor_follows_the_drift(
    hass: HomeAssistant, moves: int, level: str
) -> None:
    entry = await _setup(hass)
    cover = entry.runtime_data.cover
    cover._moves_since_sync = moves
    cover.async_write_ha_state()
    await hass.async_block_till_done()
    assert hass.states.get(SENSOR_ID).state == level
    # The attribute stays, for automations written against it.
    assert hass.states.get(COVER_ID).attributes["position_confidence"] == level


async def test_a_resync_brings_it_back_to_high(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    entry.runtime_data.cover._moves_since_sync = 12
    entry.runtime_data.cover.async_write_ha_state()
    await hass.async_block_till_done()
    assert hass.states.get(SENSOR_ID).state == "low"

    await hass.services.async_call(
        DOMAIN, "mark_closed", {"entity_id": COVER_ID}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(SENSOR_ID).state == "high"


async def test_the_drift_restored_after_a_restart_shows(hass: HomeAssistant) -> None:
    mock_restore_cache(
        hass,
        (State(COVER_ID, "open", {"current_position": 64, "moves_since_sync": 6}),),
    )
    await _setup(hass)
    assert hass.states.get(SENSOR_ID).state == "medium"


async def test_the_group_cover_has_no_sensor(hass: HomeAssistant) -> None:
    entry = await _setup(hass, "Tous", 80, group=True)
    registry = er.async_get(hass)
    domains = {
        e.domain for e in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    assert "sensor" not in domains
