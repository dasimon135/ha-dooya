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

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers import restore_state
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache,
    mock_restore_cache_with_extra_data,
)

from custom_components.dooya.const import (
    CONF_CHANNEL,
    CONF_CHECK,
    CONF_COVER_NAME,
    CONF_DOOYA_ID,
    CONF_ESPHOME_DEVICE,
    CONF_IS_GROUP,
    CONF_REPEAT_REMOTE,
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


def _make_entry(channel: int = CHANNEL, options: dict | None = None) -> MockConfigEntry:
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
        options=options or {},
    )


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> MockConfigEntry:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _fire_frame(
    hass: HomeAssistant,
    button: int,
    channel: int = CHANNEL,
    check: int | None = None,
) -> None:
    """Fire the event an ESPHome node publishes for a decoded frame."""
    data = {
        "id": f"{DOOYA_ID:06X}",
        "channel": str(channel),
        "button": str(button),
        "check": str(button if check is None else check),
    }
    hass.bus.async_fire(EVENT_DOOYA_RECEIVED, data)


def _fire_frame_without_check(hass: HomeAssistant, button: int) -> None:
    """Fire the event as a human does from Developer tools: no check field."""
    hass.bus.async_fire(
        EVENT_DOOYA_RECEIVED,
        {"id": f"{DOOYA_ID:06X}", "channel": str(CHANNEL), "button": str(button)},
    )


async def test_a_mis_decoded_frame_is_ignored(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """A frame whose check disagrees with its button never moves the estimate.

    Issue #19: a weak remote had one press decoded three times, twice with a
    check of 15. A flipped button bit is the reason this matters — UP is one
    bit from DOWN and from STOP — and it arrives with the check of the button
    that was really pressed.
    """
    entry = await _setup(hass, _make_entry())
    entry.runtime_data.cover._current_position = 50

    _fire_frame(hass, 1, check=15)
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state != "opening"

    _fire_frame(hass, 3, check=1)
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state != "closing"

    # The same press, decoded correctly, is still acted on.
    _fire_frame(hass, 1)
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == "opening"


async def test_a_frame_without_a_check_is_still_acted_on(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """An event fired by hand carries no check; there is nothing to verify."""
    entry = await _setup(hass, _make_entry())
    entry.runtime_data.cover._current_position = 50

    _fire_frame_without_check(hass, 1)
    await hass.async_block_till_done()

    assert hass.states.get(ENTITY_ID).state == "opening"


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


async def _set_position(hass: HomeAssistant, position: int) -> None:
    await hass.services.async_call(
        "cover",
        "set_cover_position",
        {"entity_id": ENTITY_ID, "position": position},
        blocking=True,
    )
    await hass.async_block_till_done()


async def test_set_position_100_at_100_still_sends_up(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """The card's Open preset resyncs a drifted estimate by driving to the stop.

    The estimate already reads 100, so no travel is scheduled: the state is
    final right after the call and nothing is left to wait for.
    """
    entry = await _setup(hass, _make_entry())
    entry.runtime_data.cover._current_position = 100

    await _set_position(hass, 100)

    state = hass.states.get(ENTITY_ID)
    assert [f["btn"] for f in frames] == [1]
    assert state.state == "open"
    assert state.attributes["current_position"] == 100


async def test_set_position_0_at_0_still_sends_down(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """The card's Closed preset resyncs a drifted estimate the same way."""
    entry = await _setup(hass, _make_entry())
    entry.runtime_data.cover._current_position = 0

    await _set_position(hass, 0)

    state = hass.states.get(ENTITY_ID)
    assert [f["btn"] for f in frames] == [3]
    assert state.state == "closed"


async def test_set_position_to_the_position_being_passed_stops(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """Asking for the position the shutter is passing stops it there.

    A long travel time keeps the estimate on the same integer between the
    read and the service call (1 % is 0.6 s). The entity property is read
    rather than the state, which only refreshes on the 1 s progress tick.
    """
    entry = await _setup(hass, _make_entry())
    cover = entry.runtime_data.cover
    cover._current_position = 0
    cover._travel_time_up = 60.0

    await hass.services.async_call(
        "cover", "open_cover", {"entity_id": ENTITY_ID}, blocking=True
    )
    await asyncio.sleep(1.0)
    passing = cover.current_cover_position
    assert 0 < passing < 100

    await _set_position(hass, passing)

    state = hass.states.get(ENTITY_ID)
    assert [f["btn"] for f in frames] == [1, 5]
    assert state.state != "opening"
    assert state.attributes["current_position"] == passing


async def test_set_position_to_an_intermediate_rest_position_sends_nothing(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """At rest between the stops there is nothing to resync: no frame."""
    entry = await _setup(hass, _make_entry())
    entry.runtime_data.cover._current_position = 40

    await _set_position(hass, 40)

    assert frames == []
    assert entry.runtime_data.cover.current_cover_position == 40


async def test_unloading_during_a_partial_move_stops_the_shutter(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """Reloading the entry mid-move sends the STOP the timer would have sent.

    The timer dies with the entity. Without this the shutter ran on to its end
    stop while the restored estimate claimed a position halfway up.
    """
    entry = await _setup(hass, _make_entry())
    entry.runtime_data.cover._current_position = 0

    await hass.services.async_call(
        "cover",
        "set_cover_position",
        {"entity_id": ENTITY_ID, "position": 90},
        blocking=True,
    )
    await asyncio.sleep(0.6)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert [f["btn"] for f in frames] == [1, 5]

    # Nothing more is transmitted once the original deadline passes.
    await asyncio.sleep(TRAVEL)
    await hass.async_block_till_done()
    assert [f["btn"] for f in frames] == [1, 5]


async def test_the_estimate_survives_a_reload_mid_move(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """After a reload mid-move the estimate is where the shutter really stopped.

    The STOP has to be sent before Home Assistant snapshots the state for
    restore, or the position saved is the one from before the shutter stopped
    and the drift of the interrupted move is lost.
    """
    entry = await _setup(hass, _make_entry())
    entry.runtime_data.cover._current_position = 0

    await hass.services.async_call(
        "cover",
        "set_cover_position",
        {"entity_id": ENTITY_ID, "position": 90},
        blocking=True,
    )
    await asyncio.sleep(0.6)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert [f["btn"] for f in frames] == [1, 5]
    state = hass.states.get(ENTITY_ID)
    # 0.6 s into a 3 s travel: short of the 90 % it was asked for.
    assert 5 <= state.attributes["current_position"] <= 45
    # It ended between the end stops, so the estimate is one move less sure.
    assert state.attributes["moves_since_sync"] == 1

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_unloading_at_rest_transmits_nothing(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """An unload with no partial move pending stays silent on the air."""
    entry = await _setup(hass, _make_entry())
    entry.runtime_data.cover._current_position = 0

    await hass.services.async_call(
        "cover", "open_cover", {"entity_id": ENTITY_ID}, blocking=True
    )
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    # A full run ends on the motor's own end stop: no STOP to send.
    assert [f["btn"] for f in frames] == [1]


async def test_a_restart_during_a_partial_move_stops_the_shutter(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """Home Assistant stopping does not unload the entry: the STOP must still go."""
    entry = await _setup(hass, _make_entry())
    entry.runtime_data.cover._current_position = 0

    await hass.services.async_call(
        "cover",
        "set_cover_position",
        {"entity_id": ENTITY_ID, "position": 90},
        blocking=True,
    )
    await asyncio.sleep(0.6)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()

    assert [f["btn"] for f in frames] == [1, 5]
    assert 5 <= hass.states.get(ENTITY_ID).attributes["current_position"] <= 45


async def test_a_reload_during_a_full_travel_keeps_the_end_stop(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """No STOP is due on a full travel; the estimate lands where the motor goes."""
    entry = await _setup(hass, _make_entry())
    entry.runtime_data.cover._current_position = 0

    await hass.services.async_call(
        "cover", "open_cover", {"entity_id": ENTITY_ID}, blocking=True
    )
    await asyncio.sleep(1.0)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert [f["btn"] for f in frames] == [1]
    assert hass.states.get(ENTITY_ID).attributes["current_position"] == 100


async def test_a_restart_during_a_full_travel_keeps_the_end_stop(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """Same on a restart: nothing transmitted, the estimate at the end stop."""
    entry = await _setup(hass, _make_entry())
    entry.runtime_data.cover._current_position = 0

    await hass.services.async_call(
        "cover", "open_cover", {"entity_id": ENTITY_ID}, blocking=True
    )
    await asyncio.sleep(1.0)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()

    assert [f["btn"] for f in frames] == [1]
    assert hass.states.get(ENTITY_ID).attributes["current_position"] == 100


async def test_a_command_during_the_auto_stop_keeps_its_own_movement(
    hass: HomeAssistant,
) -> None:
    """A command arriving while the automatic STOP transmits is not undone."""
    sent: list[int] = []
    release = asyncio.Event()

    async def _slow(call) -> None:
        sent.append(call.data["btn"])
        if call.data["btn"] == 5:
            await release.wait()

    hass.services.async_register("esphome", GATEWAY_SERVICE, _slow)

    entry = await _setup(hass, _make_entry())
    cover = entry.runtime_data.cover
    cover._current_position = 0

    await hass.services.async_call(
        "cover",
        "set_cover_position",
        {"entity_id": ENTITY_ID, "position": 20},
        blocking=True,
    )
    # Wait for the automatic STOP to be in flight, then press DOWN on the
    # remote (UP would be filtered out as an echo of our own UP).
    for _ in range(40):
        if 5 in sent:
            break
        await asyncio.sleep(0.05)
    assert 5 in sent
    _fire_frame(hass, 3)
    # Not async_block_till_done(): it would wait for the STOP held back above.
    await asyncio.sleep(0.05)
    assert hass.states.get(ENTITY_ID).state == "closing"
    release.set()
    await asyncio.sleep(0.1)

    assert hass.states.get(ENTITY_ID).state == "closing"
    assert cover._target_position == 0

    assert await hass.config_entries.async_unload(entry.entry_id)


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


async def test_mark_closed_holds_during_a_movement(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """Set as closed mid-travel ends at 0, even with asyncio debug on.

    Cancelling a timer in debug mode reads the entity's state through its
    repr, which used to recompute the travelled position over the one set.
    """
    entry = await _setup(hass, _make_entry())
    entry.runtime_data.cover._current_position = 0

    await hass.services.async_call(
        "cover", "open_cover", {"entity_id": ENTITY_ID}, blocking=True
    )
    await asyncio.sleep(1.0)
    await hass.services.async_call(
        "dooya", "mark_closed", {"entity_id": ENTITY_ID}, blocking=True
    )
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state.state == "closed"
    assert state.attributes["current_position"] == 0


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


def _stored_extra_data(hass: HomeAssistant) -> dict | None:
    """What a restore dump taken at this instant would save for the cover.

    The dump can run before any EVENT_HOMEASSISTANT_STOP listener of ours
    (it registers first for an entity added after start), so this snapshot
    is all a restart can rely on.
    """
    for stored in restore_state.async_get(hass).async_get_stored_states():
        if stored.state.entity_id == ENTITY_ID:
            return stored.extra_data.as_dict() if stored.extra_data else None
    raise AssertionError(f"{ENTITY_ID} is not in the restore snapshot")


async def test_a_restart_during_a_full_travel_saves_the_end_stop(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """The motor stops itself at the end stop, whenever the snapshot is taken."""
    entry = await _setup(hass, _make_entry())
    entry.runtime_data.cover._current_position = 0

    await hass.services.async_call(
        "cover", "open_cover", {"entity_id": ENTITY_ID}, blocking=True
    )
    await asyncio.sleep(1.0)

    extra = _stored_extra_data(hass)
    assert extra is not None
    assert extra["position"] == 100
    assert extra["moves_since_sync"] == 0


async def test_a_restart_during_a_partial_move_saves_where_the_stop_ends_it(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """The pending STOP ends a partial move short of its target, off the stops."""
    entry = await _setup(hass, _make_entry())
    entry.runtime_data.cover._current_position = 0

    await _set_position(hass, 90)
    await asyncio.sleep(0.6)

    extra = _stored_extra_data(hass)
    assert extra is not None
    assert 0 < extra["position"] < 90
    assert extra["moves_since_sync"] == 1


async def test_restore_prefers_the_extra_data_over_the_attributes(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """The attributes may be a progress tick; the extra data is the outcome."""
    mock_restore_cache_with_extra_data(
        hass,
        (
            (
                State(
                    ENTITY_ID,
                    "open",
                    {"current_position": 33, "moves_since_sync": 0},
                ),
                {"position": 100, "moves_since_sync": 0},
            ),
        ),
    )
    await _setup(hass, _make_entry())

    state = hass.states.get(ENTITY_ID)
    assert state.attributes["current_position"] == 100
    assert state.attributes["moves_since_sync"] == 0


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
    *, flagged: bool, channel: int = GROUP_CHANNEL, options: dict | None = None
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
        options={**({CONF_IS_GROUP: True} if flagged else {}), **(options or {})},
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


# ---- a group command sent from Home Assistant (issue #33, second defect) ---

OTHER_ID = 0xB032B9


def _make_sibling_entry(channel: int, name: str, dooya_id: int = DOOYA_ID):
    """A second per-channel cover of the same remote."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=name,
        data={
            CONF_ESPHOME_DEVICE: GATEWAY_SLUG,
            CONF_DOOYA_ID: dooya_id,
            CONF_CHANNEL: channel,
            CONF_CHECK: 1,
            CONF_COVER_NAME: name,
            CONF_TRAVEL_TIME_UP: TRAVEL,
            CONF_TRAVEL_TIME_DOWN: TRAVEL,
        },
    )


async def test_opening_the_group_entity_moves_the_siblings(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """The node never hears its own frame, so the fan-out has to be explicit."""
    await _setup(hass, _make_group_entry(flagged=True))
    sibling = await _setup(hass, _make_entry())
    sibling.runtime_data.cover._current_position = 0

    await hass.services.async_call(
        "cover", "open_cover", {"entity_id": GROUP_ENTITY_ID}, blocking=True
    )
    await hass.async_block_till_done()

    assert hass.states.get(ENTITY_ID).state == "opening"
    # One frame, on the group channel: the siblings are driven in Home
    # Assistant, not by 19 extra transmissions.
    assert [f["channel"] for f in frames] == [GROUP_CHANNEL]


async def test_closing_the_group_entity_moves_the_siblings(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """DOWN fans out the same way as UP."""
    await _setup(hass, _make_group_entry(flagged=True))
    sibling = await _setup(hass, _make_entry())
    sibling.runtime_data.cover._current_position = 100

    await hass.services.async_call(
        "cover", "close_cover", {"entity_id": GROUP_ENTITY_ID}, blocking=True
    )
    await hass.async_block_till_done()

    assert hass.states.get(ENTITY_ID).state == "closing"


async def test_stopping_the_group_entity_freezes_the_siblings(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """A group STOP settles each sibling on its own estimated position."""
    await _setup(hass, _make_group_entry(flagged=True))
    sibling = await _setup(hass, _make_entry())
    sibling.runtime_data.cover._current_position = 0

    await hass.services.async_call(
        "cover", "open_cover", {"entity_id": GROUP_ENTITY_ID}, blocking=True
    )
    await asyncio.sleep(TRAVEL * 0.5)
    await hass.services.async_call(
        "cover", "stop_cover", {"entity_id": GROUP_ENTITY_ID}, blocking=True
    )
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state.state == "open"
    assert 35 <= state.attributes["current_position"] <= 65, state.attributes


async def test_the_group_entity_leaves_another_remote_alone(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """The fan-out is scoped to the remote id, never to every Dooya cover."""
    await _setup(hass, _make_group_entry(flagged=True))
    stranger = await _setup(
        hass, _make_sibling_entry(CHANNEL, "Chambre", dooya_id=OTHER_ID)
    )
    stranger.runtime_data.cover._current_position = 0

    await hass.services.async_call(
        "cover", "open_cover", {"entity_id": GROUP_ENTITY_ID}, blocking=True
    )
    await hass.async_block_till_done()

    assert hass.states.get("cover.chambre").state != "opening"


async def test_a_group_command_arms_the_siblings_echo_filter(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """A second node echoing our group frame must not revive a stopped sibling.

    With more than one node in the house, the frame this entity transmits is
    heard and republished by the others. The sibling has already acted on it
    locally, so the late echo is its own transmission — exactly what
    `TxEchoFilter` is for.
    """
    await _setup(hass, _make_group_entry(flagged=True))
    sibling = await _setup(hass, _make_entry())
    sibling.runtime_data.cover._current_position = 0

    await hass.services.async_call(
        "cover", "open_cover", {"entity_id": GROUP_ENTITY_ID}, blocking=True
    )
    await asyncio.sleep(TRAVEL * 0.3)
    await hass.services.async_call(
        "cover", "stop_cover", {"entity_id": GROUP_ENTITY_ID}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == "open"

    # The other node's delayed echo of the UP we just sent.
    _fire_frame(hass, 1, channel=GROUP_CHANNEL)
    await hass.async_block_till_done()

    assert hass.states.get(ENTITY_ID).state != "opening"


# ---- repeating presses from the remote (issue #19) ----------------------

REPEAT = {CONF_REPEAT_REMOTE: True}


async def test_a_press_is_repeated_through_this_covers_node(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """With the option on, a press on the remote goes out once more."""
    entry = await _setup(hass, _make_entry(options=REPEAT))
    entry.runtime_data.cover._current_position = 0

    _fire_frame(hass, 1)
    await hass.async_block_till_done()

    assert frames == [{"dooya_id": DOOYA_ID, "channel": CHANNEL, "btn": 1, "check": 1}]
    # The press itself still moves the estimate, as it always has.
    assert hass.states.get(ENTITY_ID).state == "opening"


async def test_a_burst_from_the_remote_is_repeated_once(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """A remote sends each press several times; it goes out again only once."""
    entry = await _setup(hass, _make_entry(options=REPEAT))
    entry.runtime_data.cover._current_position = 0

    for _ in range(3):
        _fire_frame(hass, 1)
    await hass.async_block_till_done()

    assert [f["btn"] for f in frames] == [1]


async def test_home_assistants_own_command_is_never_repeated(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """A second node hears our UP; it must not be repeated, and the STOP holds.

    Issue #19: an automation repeating presses could not tell this echo from
    the remote, repeated it as a full open, and cancelled the STOP scheduled
    for the target.
    """
    entry = await _setup(hass, _make_entry(options=REPEAT))
    entry.runtime_data.cover._current_position = 0

    await hass.services.async_call(
        "cover",
        "set_cover_position",
        {"entity_id": ENTITY_ID, "position": 50},
        blocking=True,
    )
    # The other node reports our own UP, as a press would look.
    _fire_frame(hass, 1)
    await hass.async_block_till_done()
    assert [f["btn"] for f in frames] == [1]

    await asyncio.sleep(TRAVEL * 0.5 + 1.0)
    await hass.async_block_till_done()

    assert [f["btn"] for f in frames] == [1, 5]
    assert hass.states.get(ENTITY_ID).attributes["current_position"] == 50
