"""Tests for the remote's event entity: one press, one event.

Skipped automatically when pytest-homeassistant-custom-component is not
installed (e.g. on Windows, where the harness cannot run).
"""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

if sys.platform == "win32":
    pytest.skip(
        "the Home Assistant test harness does not run on Windows",
        allow_module_level=True,
    )
pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.core import HomeAssistant, callback
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dooya_rf.const import (
    CONF_CHANNEL,
    CONF_CHECK,
    CONF_COVER_NAME,
    CONF_DOOYA_ID,
    CONF_ESPHOME_DEVICE,
    CONF_IS_AWNING,
    CONF_IS_GROUP,
    CONF_TRAVEL_TIME_DOWN,
    CONF_TRAVEL_TIME_UP,
    DOMAIN,
    EVENT_DOOYA_RECEIVED,
)

GATEWAY_SERVICE = "volets_dooya_rf433_transmit_dooya"
DOOYA_ID = 0xC2D604
UP, DOWN, STOP, LED = 1, 3, 5, 0
EVENT_ID = "event.salon_remote"
CLOCK = "custom_components.dooya_rf.cover.monotonic"


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
    hass: HomeAssistant,
    name: str = "Salon",
    channel: int = 5,
    *,
    awning: bool = False,
    group: bool = False,
) -> MockConfigEntry:
    options: dict = {}
    if awning:
        options[CONF_IS_AWNING] = True
    if group:
        options[CONF_IS_GROUP] = True
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=name,
        data={
            CONF_ESPHOME_DEVICE: "volets-dooya-rf433",
            CONF_DOOYA_ID: DOOYA_ID,
            CONF_CHANNEL: channel,
            CONF_CHECK: 1,
            CONF_COVER_NAME: name,
            CONF_TRAVEL_TIME_UP: 3.0,
            CONF_TRAVEL_TIME_DOWN: 3.0,
        },
        options=options,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _frame(
    hass: HomeAssistant, button: int, channel: int = 5, check: int | None = None
) -> None:
    hass.bus.async_fire(
        EVENT_DOOYA_RECEIVED,
        {
            "id": f"{DOOYA_ID:06X}",
            "channel": str(channel),
            "button": str(button),
            "check": str(button if check is None else check),
        },
    )
    await hass.async_block_till_done()


@pytest.fixture
def fired(hass: HomeAssistant) -> dict[str, list[str]]:
    """Record every event the remote entities fire, per entity."""
    seen: dict[str, list[str]] = {}

    @callback
    def _record(event) -> None:
        new = event.data["new_state"]
        if new is None or not new.entity_id.startswith("event."):
            return
        if new.attributes.get("event_type") is None:
            return
        old = event.data["old_state"]
        if old is not None and old.state == new.state:
            return
        seen.setdefault(new.entity_id, []).append(new.attributes["event_type"])

    hass.bus.async_listen("state_changed", _record)
    return seen


async def test_the_entity_exists_with_the_remote_buttons(
    hass: HomeAssistant,
) -> None:
    await _setup(hass)
    state = hass.states.get(EVENT_ID)
    assert state is not None
    assert state.attributes["event_types"] == ["up", "stop", "down"]
    assert state.attributes["device_class"] == "button"


@pytest.mark.parametrize(
    ("button", "event_type"), [(UP, "up"), (STOP, "stop"), (DOWN, "down")]
)
async def test_a_press_fires_its_button(
    hass: HomeAssistant, fired: dict, button: int, event_type: str
) -> None:
    await _setup(hass)
    await _frame(hass, button)
    assert fired[EVENT_ID] == [event_type]


async def test_a_burst_fires_once(hass: HomeAssistant, fired: dict) -> None:
    """A remote sends each press as several identical frames."""
    await _setup(hass)
    for now in (100.0, 100.05, 100.1):
        with patch(CLOCK, return_value=now):
            await _frame(hass, DOWN)
    assert fired[EVENT_ID] == ["down"]


async def test_a_second_press_after_a_pause_fires_again(
    hass: HomeAssistant, fired: dict
) -> None:
    await _setup(hass)
    with patch(CLOCK, return_value=100.0):
        await _frame(hass, DOWN)
    with patch(CLOCK, return_value=105.0):
        await _frame(hass, DOWN)
    assert len(fired[EVENT_ID]) == 2


async def test_our_own_command_heard_back_fires_nothing(
    hass: HomeAssistant, fired: dict
) -> None:
    """Home Assistant's UP, heard by a node, is an echo, not a remote press."""
    await _setup(hass)
    await hass.services.async_call(
        "cover", "open_cover", {"entity_id": "cover.salon"}, blocking=True
    )
    await _frame(hass, UP)
    assert EVENT_ID not in fired


async def test_another_remote_or_channel_fires_nothing(
    hass: HomeAssistant, fired: dict
) -> None:
    await _setup(hass)
    await _frame(hass, UP, channel=6)
    assert EVENT_ID not in fired


async def test_a_misdecoded_frame_fires_nothing(
    hass: HomeAssistant, fired: dict
) -> None:
    await _setup(hass)
    await _frame(hass, UP, check=9)
    assert EVENT_ID not in fired


async def test_the_led_button_fires_nothing(hass: HomeAssistant, fired: dict) -> None:
    await _setup(hass)
    await _frame(hass, LED)
    assert EVENT_ID not in fired


async def test_an_awning_reports_the_remote_button(
    hass: HomeAssistant, fired: dict
) -> None:
    """DOWN deploys an awning, but the event says what was pressed."""
    await _setup(hass, awning=True)
    await _frame(hass, DOWN)
    assert fired[EVENT_ID] == ["down"]


async def test_the_group_button_fires_on_the_group_and_its_shutters(
    hass: HomeAssistant, fired: dict
) -> None:
    await _setup(hass)
    await _setup(hass, "Tous", 80, group=True)
    await _frame(hass, UP, channel=80)
    assert fired[EVENT_ID] == ["up"]
    assert fired["event.tous_remote"] == ["up"]
