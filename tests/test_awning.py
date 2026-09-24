"""Tests for awnings: DOWN deploys them, and deployed is open (issue #50).

Home Assistant's convention for `CoverDeviceClass.AWNING` is open = deployed:
the core Overkiz integration maps `open_cover` to DEPLOY and `close_cover` to
UNDEPLOY. A Dooya remote deploys an awning with DOWN, so for a cover flagged as
an awning every mapping between a button and a direction of travel is swapped.
Buttons stay physical, directions stay semantic.

Skipped automatically when pytest-homeassistant-custom-component is not
installed (e.g. on Windows, where the harness cannot run).
"""

from __future__ import annotations

import asyncio
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
    CONF_IS_AWNING,
    CONF_IS_GROUP,
    CONF_REPEAT_COUNT,
    CONF_TRAVEL_TIME_DOWN,
    CONF_TRAVEL_TIME_UP,
    DOMAIN,
    EVENT_DOOYA_RECEIVED,
)

GATEWAY_SLUG = "volets-dooya-rf433"
GATEWAY_SERVICE = "volets_dooya_rf433_transmit_dooya"
DOOYA_ID = 0xC2D604
TRAVEL = 3.0

UP = 1
DOWN = 3
STOP = 5

AWNING_ID = "cover.terrasse"
SHUTTER_ID = "cover.salon"
GROUP_ID = "cover.all_shutters"
GROUP_CHANNEL = 80


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Make custom_components/ visible to the test hass instance."""
    return


@pytest.fixture
def frames(hass: HomeAssistant) -> list[dict]:
    """Register the gateway service and record every transmitted frame."""
    calls: list[dict] = []

    @callback
    def _record(call) -> None:
        calls.append(dict(call.data))

    hass.services.async_register("esphome", GATEWAY_SERVICE, _record)
    return calls


def _entry(
    name: str, channel: int, *, awning: bool = False, group: bool = False
) -> MockConfigEntry:
    options: dict = {}
    if awning:
        options[CONF_IS_AWNING] = True
    if group:
        options[CONF_IS_GROUP] = True
    return MockConfigEntry(
        domain=DOMAIN,
        title=name,
        data={
            CONF_ESPHOME_DEVICE: GATEWAY_SLUG,
            CONF_DOOYA_ID: DOOYA_ID,
            CONF_CHANNEL: channel,
            CONF_CHECK: 1,
            CONF_COVER_NAME: name,
            CONF_TRAVEL_TIME_UP: TRAVEL,
            CONF_TRAVEL_TIME_DOWN: TRAVEL,
        },
        options=options,
    )


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> MockConfigEntry:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _fire_frame(hass: HomeAssistant, button: int, channel: int) -> None:
    hass.bus.async_fire(
        EVENT_DOOYA_RECEIVED,
        {
            "id": f"{DOOYA_ID:06X}",
            "channel": str(channel),
            "button": str(button),
            "check": str(button),
        },
    )


# ---- the entity ------------------------------------------------------------


async def test_a_flagged_cover_is_an_awning(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """The device class is what the frontend, voice and automations read."""
    await _setup(hass, _entry("Terrasse", 5, awning=True))

    assert hass.states.get(AWNING_ID).attributes["device_class"] == "awning"


async def test_an_unflagged_cover_stays_a_shutter(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """Existing entries carry no flag and must not change."""
    await _setup(hass, _entry("Salon", 5))

    assert hass.states.get(SHUTTER_ID).attributes["device_class"] == "shutter"


async def test_opening_an_awning_sends_down(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """Open is deployed, and DOWN is what deploys a Dooya awning."""
    entry = await _setup(hass, _entry("Terrasse", 5, awning=True))
    entry.runtime_data.cover._current_position = 0

    await hass.services.async_call(
        "cover", "open_cover", {"entity_id": AWNING_ID}, blocking=True
    )
    await hass.async_block_till_done()

    assert [f["btn"] for f in frames] == [DOWN]
    assert hass.states.get(AWNING_ID).state == "opening"


async def test_closing_an_awning_sends_up(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """Closed is retracted, which is UP."""
    entry = await _setup(hass, _entry("Terrasse", 5, awning=True))
    entry.runtime_data.cover._current_position = 100

    await hass.services.async_call(
        "cover", "close_cover", {"entity_id": AWNING_ID}, blocking=True
    )
    await hass.async_block_till_done()

    assert [f["btn"] for f in frames] == [UP]
    assert hass.states.get(AWNING_ID).state == "closing"


async def test_a_full_deploy_ends_open_at_100(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """The estimate runs in the semantic direction: deployed is 100 %."""
    entry = await _setup(hass, _entry("Terrasse", 5, awning=True))
    entry.runtime_data.cover._current_position = 0

    await hass.services.async_call(
        "cover", "open_cover", {"entity_id": AWNING_ID}, blocking=True
    )
    await asyncio.sleep(TRAVEL + 1.0)
    await hass.async_block_till_done()

    state = hass.states.get(AWNING_ID)
    assert state.state == "open"
    assert state.attributes["current_position"] == 100
    assert [f["btn"] for f in frames] == [DOWN]


async def test_setting_an_awning_position_deploys_with_down(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """Moving towards a higher position deploys, then STOP at the target."""
    entry = await _setup(hass, _entry("Terrasse", 5, awning=True))
    entry.runtime_data.cover._current_position = 0

    await hass.services.async_call(
        "cover",
        "set_cover_position",
        {"entity_id": AWNING_ID, "position": 50},
        blocking=True,
    )
    await asyncio.sleep(TRAVEL * 0.5 + 1.0)
    await hass.async_block_till_done()

    assert [f["btn"] for f in frames] == [DOWN, STOP]
    assert hass.states.get(AWNING_ID).attributes["current_position"] == 50


async def test_set_position_100_on_a_deployed_awning_still_sends_down(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """The Open preset resyncs an awning with its own deploy button."""
    entry = await _setup(hass, _entry("Terrasse", 5, awning=True))
    entry.runtime_data.cover._current_position = 100

    await hass.services.async_call(
        "cover",
        "set_cover_position",
        {"entity_id": AWNING_ID, "position": 100},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert [f["btn"] for f in frames] == [DOWN]
    assert hass.states.get(AWNING_ID).state == "open"


async def test_down_on_the_remote_opens_an_awning(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """A press on the physical remote is read through the same swap."""
    entry = await _setup(hass, _entry("Terrasse", 5, awning=True))
    entry.runtime_data.cover._current_position = 0

    _fire_frame(hass, DOWN, channel=5)
    await hass.async_block_till_done()

    assert hass.states.get(AWNING_ID).state == "opening"
    assert frames == []


async def test_calibrating_an_awning_open_deploys_it(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """Calibration measures the opening time, which on an awning is DOWN."""
    entry = await _setup(hass, _entry("Terrasse", 5, awning=True))
    cover = entry.runtime_data.cover
    cover._current_position = 0

    await cover.async_start_calibration(1)
    await hass.async_block_till_done()
    await asyncio.sleep(1.3)
    await hass.services.async_call(
        "cover", "stop_cover", {"entity_id": AWNING_ID}, blocking=True
    )
    await hass.async_block_till_done()

    assert [f["btn"] for f in frames] == [DOWN, STOP]
    assert 1.0 <= entry.options[CONF_TRAVEL_TIME_UP] <= 3.0


# ---- one remote driving shutters and an awning (issue #33 fan-out) ---------


async def test_a_group_open_moves_each_sibling_by_its_own_mapping(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """The common button sends one physical UP: shutters open, the awning closes."""
    await _setup(hass, _entry("All shutters", GROUP_CHANNEL, group=True))
    shutter = await _setup(hass, _entry("Salon", 5))
    awning = await _setup(hass, _entry("Terrasse", 6, awning=True))
    shutter.runtime_data.cover._current_position = 0
    awning.runtime_data.cover._current_position = 100

    await hass.services.async_call(
        "cover", "open_cover", {"entity_id": GROUP_ID}, blocking=True
    )
    await hass.async_block_till_done()

    assert [f["btn"] for f in frames] == [UP]
    assert hass.states.get(SHUTTER_ID).state == "opening"
    assert hass.states.get(AWNING_ID).state == "closing"


async def test_a_group_frame_from_the_remote_moves_each_sibling_by_its_own_mapping(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """The same holds for the physical common button heard by the node."""
    await _setup(hass, _entry("All shutters", GROUP_CHANNEL, group=True))
    shutter = await _setup(hass, _entry("Salon", 5))
    awning = await _setup(hass, _entry("Terrasse", 6, awning=True))
    shutter.runtime_data.cover._current_position = 100
    awning.runtime_data.cover._current_position = 0

    _fire_frame(hass, DOWN, channel=GROUP_CHANNEL)
    await hass.async_block_till_done()

    assert hass.states.get(SHUTTER_ID).state == "closing"
    assert hass.states.get(AWNING_ID).state == "opening"


# ---- the flag in the config and options flows ------------------------------


async def test_manual_entry_can_create_an_awning(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """The flag is offered where the cover is named."""
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
            CONF_COVER_NAME: "Terrasse",
            CONF_DOOYA_ID: "00C2D604",
            CONF_CHANNEL: 5,
            CONF_TRAVEL_TIME_UP: 25.0,
            CONF_TRAVEL_TIME_DOWN: 22.0,
            CONF_IS_AWNING: True,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_IS_AWNING] is True


async def test_learning_a_remote_can_create_an_awning(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """Same flag on the confirm step that follows a learned press."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ESPHOME_DEVICE: GATEWAY_SLUG}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"method": "learn"}
    )
    assert result["type"] is FlowResultType.SHOW_PROGRESS

    _fire_frame(hass, DOWN, channel=5)
    await hass.async_block_till_done()

    result = await hass.config_entries.flow.async_configure(result["flow_id"])
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_COVER_NAME: "Terrasse",
            CONF_TRAVEL_TIME_UP: 25.0,
            CONF_TRAVEL_TIME_DOWN: 22.0,
            CONF_IS_AWNING: True,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_DOOYA_ID] == DOOYA_ID
    assert result["data"][CONF_IS_AWNING] is True


async def test_an_entry_created_without_the_flag_is_not_an_awning(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """Leaving the box unticked records a shutter, explicitly."""
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
            CONF_DOOYA_ID: "00D1C917",
            CONF_CHANNEL: 5,
            CONF_TRAVEL_TIME_UP: 20.0,
            CONF_TRAVEL_TIME_DOWN: 18.0,
        },
    )
    await hass.async_block_till_done()

    assert result["data"][CONF_IS_AWNING] is False


async def test_options_can_turn_an_existing_cover_into_an_awning(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """An entry created before this option existed is fixed from its options."""
    entry = await _setup(hass, _entry("Terrasse", 5))

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_ESPHOME_DEVICE: GATEWAY_SLUG,
            CONF_TRAVEL_TIME_UP: 20.0,
            CONF_TRAVEL_TIME_DOWN: 20.0,
            CONF_REPEAT_COUNT: 1,
            CONF_IS_GROUP: False,
            CONF_IS_AWNING: True,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_IS_AWNING] is True
    # The options update reloads the entry: the entity comes back as an awning.
    assert hass.states.get(AWNING_ID).attributes["device_class"] == "awning"
