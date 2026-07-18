"""Tests for the Dooya cover entity (requires the HA test harness).

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

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
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
    gateway_issue_id,
)

GATEWAY_SLUG = "volets-dooya-rf433"
GATEWAY_SERVICE = "volets_dooya_rf433_transmit_dooya"
ENTITY_ID = "cover.salon"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Make custom_components/ visible to the test hass instance."""
    return


def _make_entry() -> MockConfigEntry:
    return MockConfigEntry(
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


async def _setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_creates_main_cover_entity(hass: HomeAssistant) -> None:
    """The cover is the main entity of its device (no doubled name)."""
    entry = _make_entry()
    await _setup_entry(hass, entry)

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    # _attr_name = None + has_entity_name: the friendly name is exactly the
    # device name, not "Salon Salon".
    assert state.name == "Salon"

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_open_with_gateway_transmits_and_moves(hass: HomeAssistant) -> None:
    """Opening calls the ESPHome service and starts the estimated motion."""
    calls: list[dict] = []

    @callback
    def _record(call) -> None:
        calls.append(dict(call.data))

    hass.services.async_register("esphome", GATEWAY_SERVICE, _record)

    entry = _make_entry()
    await _setup_entry(hass, entry)

    await hass.services.async_call(
        "cover", "open_cover", {"entity_id": ENTITY_ID}, blocking=True
    )
    await hass.async_block_till_done()

    assert calls == [
        {"dooya_id": 0x00D1C917, "channel": 5, "btn": 1, "check": 1}
    ]
    state = hass.states.get(ENTITY_ID)
    assert state.state == "opening"

    # Unload cancels the motion timers cleanly.
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_open_without_gateway_raises_and_creates_issue(
    hass: HomeAssistant,
) -> None:
    """A missing gateway service raises and does not fake a movement."""
    entry = _make_entry()
    await _setup_entry(hass, entry)

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "cover", "open_cover", {"entity_id": ENTITY_ID}, blocking=True
        )
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state.state != "opening"

    issue_registry = ir.async_get(hass)
    assert (
        issue_registry.async_get_issue(DOMAIN, gateway_issue_id(entry.entry_id))
        is not None
    )

    # The repair issue is cleared once the service is back and a command
    # succeeds.
    hass.services.async_register("esphome", GATEWAY_SERVICE, lambda call: None)
    await hass.services.async_call(
        "cover", "close_cover", {"entity_id": ENTITY_ID}, blocking=True
    )
    await hass.async_block_till_done()
    assert (
        issue_registry.async_get_issue(DOMAIN, gateway_issue_id(entry.entry_id))
        is None
    )

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_unload_clears_repair_issue(hass: HomeAssistant) -> None:
    """Unloading the entry removes its pending repair issue."""
    entry = _make_entry()
    await _setup_entry(hass, entry)

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "cover", "open_cover", {"entity_id": ENTITY_ID}, blocking=True
        )
    await hass.async_block_till_done()

    assert await hass.config_entries.async_unload(entry.entry_id)
    issue_registry = ir.async_get(hass)
    assert (
        issue_registry.async_get_issue(DOMAIN, gateway_issue_id(entry.entry_id))
        is None
    )
