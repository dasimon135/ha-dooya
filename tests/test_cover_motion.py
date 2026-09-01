"""Tests for the Dooya motion state machine, echo filter and calibration.

Skipped automatically when pytest-homeassistant-custom-component is not
installed (e.g. on Windows, where the harness cannot run).

Timing note: these tests use short *real* travel times and real sleeps rather
than a frozen clock. `_refresh_position` reads `time.monotonic()` while
`async_call_later` uses the event-loop clock; freezing time desynchronises the
two and produces off-by-a-few positions that are artefacts, not behaviour.
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

from homeassistant.core import HomeAssistant, State, callback
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache,
)

from custom_components.dooya.const import (
    CONF_CHANNEL,
    CONF_CHECK,
    CONF_COVER_NAME,
    CONF_DOOYA_ID,
    CONF_ESPHOME_DEVICE,
    CONF_IS_GROUP,
    CONF_TRAVEL_TIME_DOWN,
    CONF_TRAVEL_TIME_UP,
    DOMAIN,
    EVENT_DOOYA_RECEIVED,
)

GATEWAY_SLUG = "volets-dooya-rf433"
GATEWAY_SERVICE = "volets_dooya_rf433_transmit_dooya"
ENTITY_ID = "cover.salon"
DOOYA_ID = 0xD1C917
CHANNEL = 5
TRAVEL = 3.0


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


def _make_entry(channel: int = CHANNEL) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Salon",
        data={
            CONF_ESPHOME_DEVICE: GATEWAY_SLUG,
            CONF_DOOYA_ID: DOOYA_ID,
            CONF_CHANNEL: channel,
            CONF_CHECK: 1,
            CONF_COVER_NAME: "Salon",
            CONF_TRAVEL_TIME_UP: TRAVEL,
            CONF_TRAVEL_TIME_DOWN: TRAVEL,
        },
    )


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> MockConfigEntry:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _fire_frame(hass: HomeAssistant, button: int, channel: int = CHANNEL) -> None:
    """Fire the event an ESPHome node publishes for a decoded frame."""
    hass.bus.async_fire(
        EVENT_DOOYA_RECEIVED,
        {
            "id": f"{DOOYA_ID:06X}",
            "channel": str(channel),
            "button": str(button),
            "check": str(button),
        },
    )


# ---- estimated motion ---------------------------------------------------


async def test_full_open_reaches_the_end_stop_and_resyncs(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """A full open settles at 100 %, sends no STOP and resets the drift counter."""
    entry = await _setup(hass, _make_entry())
    entry.runtime_data.cover._current_position = 0

    await hass.services.async_call(
        "cover", "open_cover", {"entity_id": ENTITY_ID}, blocking=True
    )
    await asyncio.sleep(TRAVEL + 1.0)
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state.state == "open"
    assert state.attributes["current_position"] == 100
    # Reaching an end stop resynchronises the estimate.
    assert state.attributes["moves_since_sync"] == 0
    assert [f["btn"] for f in frames] == [1]


async def test_partial_move_sends_stop_at_the_target(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """A partial set_position transmits STOP when the target is reached."""
    entry = await _setup(hass, _make_entry())
    entry.runtime_data.cover._current_position = 0

    await hass.services.async_call(
        "cover",
        "set_cover_position",
        {"entity_id": ENTITY_ID, "position": 50},
        blocking=True,
    )
    await asyncio.sleep(TRAVEL * 0.5 + 1.0)
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert [f["btn"] for f in frames] == [1, 5]
    assert state.attributes["current_position"] == 50
    # Stopping between the end stops degrades confidence in the estimate.
    assert state.attributes["moves_since_sync"] == 1


async def test_user_stop_cancels_the_scheduled_auto_stop(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """A manual STOP mid-move must not be followed by the automatic one."""
    entry = await _setup(hass, _make_entry())
    entry.runtime_data.cover._current_position = 0

    await hass.services.async_call(
        "cover",
        "set_cover_position",
        {"entity_id": ENTITY_ID, "position": 90},
        blocking=True,
    )
    await asyncio.sleep(0.6)
    await hass.services.async_call(
        "cover", "stop_cover", {"entity_id": ENTITY_ID}, blocking=True
    )
    stopped_at = hass.states.get(ENTITY_ID).attributes["current_position"]

    await asyncio.sleep(TRAVEL)
    await hass.async_block_till_done()

    assert [f["btn"] for f in frames] == [1, 5]
    assert hass.states.get(ENTITY_ID).attributes["current_position"] == stopped_at


# ---- physical remote / echo suppression ---------------------------------


async def test_physical_remote_press_starts_the_estimate(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """An UP frame from the real remote resyncs the estimated motion."""
    entry = await _setup(hass, _make_entry())
    entry.runtime_data.cover._current_position = 0

    _fire_frame(hass, 1)
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == "opening"

    await asyncio.sleep(TRAVEL * 0.5)
    await hass.async_block_till_done()
    # The written state lags by up to one progress tick (1 s), which is a third
    # of the travel at this deliberately short TRAVEL — hence the wide band.
    position = hass.states.get(ENTITY_ID).attributes["current_position"]
    assert 25 <= position <= 70, position
    # The remote transmits on its own: nothing is sent by the gateway.
    assert frames == []


async def test_echo_of_our_own_transmission_is_ignored(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """A frame echoed by another node must not restart the motion.

    Without this, the echo of our own UP would cancel the delayed STOP of a
    partial move and send the shutter to its hard limit.
    """
    entry = await _setup(hass, _make_entry())
    cover = entry.runtime_data.cover
    cover._current_position = 0

    await hass.services.async_call(
        "cover",
        "set_cover_position",
        {"entity_id": ENTITY_ID, "position": 50},
        blocking=True,
    )
    target = cover._target_position

    _fire_frame(hass, 1)  # another node hears our own UP
    await hass.async_block_till_done()

    # The partial target survived the echo.
    assert cover._target_position == target == 50

    await asyncio.sleep(TRAVEL * 0.5 + 1.0)
    await hass.async_block_till_done()
    assert [f["btn"] for f in frames] == [1, 5]
    assert hass.states.get(ENTITY_ID).attributes["current_position"] == 50


async def test_broadcast_frame_moves_a_per_channel_cover(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """Channel 0 frames drive every shutter paired with the same remote."""
    entry = await _setup(hass, _make_entry())
    entry.runtime_data.cover._current_position = 0

    _fire_frame(hass, 1, channel=0)
    await hass.async_block_till_done()

    assert hass.states.get(ENTITY_ID).state == "opening"


async def test_frame_for_another_channel_is_ignored(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """A frame addressed to a sibling shutter must not move this one."""
    entry = await _setup(hass, _make_entry())
    entry.runtime_data.cover._current_position = 0

    _fire_frame(hass, 1, channel=CHANNEL + 1)
    await hass.async_block_till_done()

    assert hass.states.get(ENTITY_ID).state != "opening"


async def test_malformed_frame_is_ignored(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """A frame with missing or unparsable fields must not raise."""
    entry = await _setup(hass, _make_entry())
    entry.runtime_data.cover._current_position = 0

    hass.bus.async_fire(EVENT_DOOYA_RECEIVED, {"id": "nope", "channel": "x"})
    hass.bus.async_fire(EVENT_DOOYA_RECEIVED, {})
    await hass.async_block_till_done()

    assert hass.states.get(ENTITY_ID).state != "opening"


# ---- calibration assistant ----------------------------------------------


async def test_calibration_measures_and_saves_the_travel_time(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """Calibrate up: UP, then the STOP press writes the measured time."""
    entry = await _setup(hass, _make_entry())
    cover = entry.runtime_data.cover
    cover._current_position = 0  # fully closed, as calibrate-up requires

    await cover.async_start_calibration(1)
    await hass.async_block_till_done()
    assert cover._calibrating == 1

    # The measurement must exceed the 1 s plausibility floor.
    await asyncio.sleep(1.3)
    await hass.services.async_call(
        "cover", "stop_cover", {"entity_id": ENTITY_ID}, blocking=True
    )
    await hass.async_block_till_done()

    measured = entry.options[CONF_TRAVEL_TIME_UP]
    assert 1.0 <= measured <= 3.0, measured
    assert cover._calibrating == 0
    assert [f["btn"] for f in frames] == [1, 5]


async def test_calibration_refused_away_from_the_end_stop(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """Calibrating up from a half-open shutter would measure a partial travel."""
    entry = await _setup(hass, _make_entry())
    cover = entry.runtime_data.cover
    cover._current_position = 50

    await cover.async_start_calibration(1)
    await hass.async_block_till_done()

    assert cover._calibrating == 0
    # Nothing was transmitted: the shutter must not move for a refused measure.
    assert frames == []


async def test_calibration_ignores_an_implausible_measure(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """A STOP pressed immediately measures noise, not a travel time."""
    entry = await _setup(hass, _make_entry())
    cover = entry.runtime_data.cover
    cover._current_position = 0

    await cover.async_start_calibration(1)
    await hass.async_block_till_done()

    # Well under the 1 s floor.
    await hass.services.async_call(
        "cover", "stop_cover", {"entity_id": ENTITY_ID}, blocking=True
    )
    await hass.async_block_till_done()

    assert cover._calibrating == 0
    assert CONF_TRAVEL_TIME_UP not in entry.options


async def test_calibration_is_closed_by_the_physical_remote(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """Pressing STOP on the real remote ends the measurement too."""
    entry = await _setup(hass, _make_entry())
    cover = entry.runtime_data.cover
    cover._current_position = 100  # fully open, as calibrate-down requires

    await cover.async_start_calibration(-1)
    await hass.async_block_till_done()

    await asyncio.sleep(1.3)
    _fire_frame(hass, 5)
    await hass.async_block_till_done()

    assert cover._calibrating == 0
    assert 1.0 <= entry.options[CONF_TRAVEL_TIME_DOWN] <= 3.0


# ---- manual recalibration and restore -----------------------------------


async def test_set_known_position_resyncs_without_transmitting(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """Telling HA where the shutter really is clears the accumulated drift."""
    entry = await _setup(hass, _make_entry())
    cover = entry.runtime_data.cover
    cover._current_position = 10
    cover._moves_since_sync = 7

    await hass.services.async_call(
        DOMAIN,
        "set_known_position",
        {"entity_id": ENTITY_ID, "position": 42},
        blocking=True,
    )
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state.attributes["current_position"] == 42
    assert state.attributes["moves_since_sync"] == 0
    assert state.attributes["position_confidence"] == "high"
    assert frames == []


async def test_position_and_drift_are_restored_after_a_restart(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """The estimate survives a restart, including its confidence."""
    mock_restore_cache(
        hass,
        (
            State(
                ENTITY_ID,
                "open",
                {"current_position": 64, "moves_since_sync": 6},
            ),
        ),
    )
    await _setup(hass, _make_entry())

    state = hass.states.get(ENTITY_ID)
    assert state.attributes["current_position"] == 64
    assert state.attributes["moves_since_sync"] == 6
    assert state.attributes["position_confidence"] == "medium"


# ---- broadcast entity ---------------------------------------------------


async def test_broadcast_entity_exposes_no_position(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """Channel 0 drives every shutter, so a per-shutter estimate is meaningless."""
    await _setup(hass, _make_entry(channel=0))

    state = hass.states.get(ENTITY_ID)
    assert state.attributes.get("current_position") is None
    assert "moves_since_sync" not in state.attributes
    # OPEN | CLOSE | STOP, without SET_POSITION.
    assert state.attributes["supported_features"] == 11

    await hass.services.async_call(
        "cover", "open_cover", {"entity_id": ENTITY_ID}, blocking=True
    )
    await hass.async_block_till_done()
    assert [f["btn"] for f in frames] == [1]
    assert [f["channel"] for f in frames] == [0]


# ---- a group channel that is not 0 (issue #33) --------------------------

GROUP_CHANNEL = 80
GROUP_ENTITY_ID = "cover.all_shutters"


def _make_group_entry(
    *, flagged: bool, channel: int = GROUP_CHANNEL
) -> MockConfigEntry:
    """A second cover of the same remote, standing for its common button."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="All shutters",
        data={
            CONF_ESPHOME_DEVICE: GATEWAY_SLUG,
            CONF_DOOYA_ID: DOOYA_ID,
            CONF_CHANNEL: channel,
            CONF_CHECK: 1,
            CONF_COVER_NAME: "All shutters",
            CONF_TRAVEL_TIME_UP: TRAVEL,
            CONF_TRAVEL_TIME_DOWN: TRAVEL,
        },
        options={CONF_IS_GROUP: True} if flagged else {},
    )


async def test_a_flagged_group_cover_makes_its_channel_move_the_siblings(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """The remote's common button need not be on channel 0 (issue #33)."""
    await _setup(hass, _make_group_entry(flagged=True))
    entry = await _setup(hass, _make_entry())
    entry.runtime_data.cover._current_position = 0

    _fire_frame(hass, 1, channel=GROUP_CHANNEL)
    await hass.async_block_till_done()

    assert hass.states.get(ENTITY_ID).state == "opening"


async def test_an_unflagged_cover_does_not_make_its_channel_a_group_channel(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """Without the flag, channel 80 is an ordinary sibling and must not fan out."""
    await _setup(hass, _make_group_entry(flagged=False))
    entry = await _setup(hass, _make_entry())
    entry.runtime_data.cover._current_position = 0

    _fire_frame(hass, 1, channel=GROUP_CHANNEL)
    await hass.async_block_till_done()

    assert hass.states.get(ENTITY_ID).state != "opening"


async def test_channel_zero_still_groups_when_no_cover_is_flagged(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """Installations predating the flag keep their channel-0 behaviour."""
    entry = await _setup(hass, _make_entry())
    entry.runtime_data.cover._current_position = 0

    _fire_frame(hass, 1, channel=0)
    await hass.async_block_till_done()

    assert hass.states.get(ENTITY_ID).state == "opening"


async def test_a_flagged_group_cover_exposes_no_position(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """The group role, not the channel number, is what drops the estimate."""
    await _setup(hass, _make_group_entry(flagged=True))

    state = hass.states.get(GROUP_ENTITY_ID)
    assert state.attributes.get("current_position") is None
    # OPEN | CLOSE | STOP, without SET_POSITION.
    assert state.attributes["supported_features"] == 11


async def test_an_unflagged_cover_on_the_same_channel_keeps_its_position(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """Channel 80 alone must not cost a shutter its position estimate."""
    await _setup(hass, _make_group_entry(flagged=False))

    state = hass.states.get(GROUP_ENTITY_ID)
    # OPEN | CLOSE | STOP | SET_POSITION.
    assert state.attributes["supported_features"] == 15


# ---- state-write hygiene -------------------------------------------------


async def test_reading_state_does_not_reenter_the_state_write(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """Cover properties must not write state while HA is building a state.

    HA reads is_closed / is_opening / is_closing / current_cover_position
    inside `_async_write_ha_state`. If those reads ended the movement, the
    write would re-enter itself and a plain state read could cancel the
    pending STOP of a partial move.
    """
    entry = await _setup(hass, _make_entry())
    cover = entry.runtime_data.cover

    # A movement whose travel time has fully elapsed: the worst case for a
    # property read, since the estimate has reached its target.
    cover._current_position = 0
    cover._movement_direction = 1
    cover._movement_start_position = 0.0
    cover._movement_start_time = cover._movement_start_time or 0.0
    cover._target_position = 100
    from time import monotonic

    cover._movement_start_time = monotonic() - (TRAVEL * 10)

    depth = {"current": 0, "max": 0}
    original = type(cover).async_write_ha_state

    def _tracking(self) -> None:
        depth["current"] += 1
        depth["max"] = max(depth["max"], depth["current"])
        try:
            original(self)
        finally:
            depth["current"] -= 1

    type(cover).async_write_ha_state = _tracking
    try:
        cover.async_write_ha_state()
    finally:
        type(cover).async_write_ha_state = original

    assert depth["max"] == 1, f"re-entrant state write, depth={depth['max']}"


async def test_reading_position_does_not_drop_a_pending_stop(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """Polling the entity mid-move must not cancel the scheduled STOP."""
    entry = await _setup(hass, _make_entry())
    cover = entry.runtime_data.cover
    cover._current_position = 0

    await hass.services.async_call(
        "cover",
        "set_cover_position",
        {"entity_id": ENTITY_ID, "position": 50},
        blocking=True,
    )

    # Diagnostics and templates read the entity object directly.
    for _ in range(40):
        _ = cover.current_cover_position
        _ = cover.is_closed
        _ = cover.is_opening
        await asyncio.sleep(0.05)

    await asyncio.sleep(TRAVEL * 0.5 + 1.0)
    await hass.async_block_till_done()

    assert [f["btn"] for f in frames] == [1, 5], "the STOP frame was lost"
    assert hass.states.get(ENTITY_ID).attributes["current_position"] == 50
