"""Tests for the Dooya button platform (requires the HA test harness).

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
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dooya.const import (
    CONF_CHANNEL,
    CONF_CHECK,
    CONF_COVER_NAME,
    CONF_DOOYA_ID,
    CONF_ESPHOME_DEVICE,
    CONF_FAVORITE_POSITION,
    CONF_TRAVEL_TIME_DOWN,
    CONF_TRAVEL_TIME_UP,
    DOMAIN,
)

GATEWAY_SLUG = "volets-dooya-rf433"
GATEWAY_SERVICE = "volets_dooya_rf433_transmit_dooya"
COVER_ENTITY_ID = "cover.salon"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Make custom_components/ visible to the test hass instance."""
    return


def _make_entry(**options) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Salon",
        data={
            CONF_ESPHOME_DEVICE: GATEWAY_SLUG,
            CONF_DOOYA_ID: 0x00D1C917,
            CONF_CHANNEL: 5,
            CONF_CHECK: 7,
            CONF_COVER_NAME: "Salon",
            CONF_TRAVEL_TIME_UP: 20.0,
            CONF_TRAVEL_TIME_DOWN: 18.0,
        },
        options=options,
    )


async def _setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _button_id(hass: HomeAssistant, entry: MockConfigEntry, key: str) -> str | None:
    """Resolve a button entity id by unique id, not by its translated name.

    Entity ids derive from the *translated* entity name, so matching on the
    name would break the moment a locale changes; the unique id suffix is the
    stable contract (see button.py::DooyaButtonBase).
    """
    registry = er.async_get(hass)
    for regentry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if regentry.unique_id == f"{entry.entry_id}_{key}":
            return regentry.entity_id
    return None


async def test_recalibration_buttons_exist(hass: HomeAssistant) -> None:
    """The four recalibration buttons are created for every entry."""
    entry = _make_entry()
    await _setup_entry(hass, entry)

    for key in ("mark_open", "mark_closed", "calibrate_up", "calibrate_down"):
        assert _button_id(hass, entry, key) is not None, key

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_favorite_button_absent_without_option(hass: HomeAssistant) -> None:
    """No favorite position configured means no favorite button."""
    entry = _make_entry()
    await _setup_entry(hass, entry)

    assert _button_id(hass, entry, "favorite") is None

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_favorite_button_appears_after_options_change(
    hass: HomeAssistant,
) -> None:
    """Setting a favorite position adds the button without a restart.

    This also covers the entry update listener in __init__.py: the button can
    only appear because changing the options reloads the entry.
    """
    entry = _make_entry()
    await _setup_entry(hass, entry)
    assert _button_id(hass, entry, "favorite") is None

    hass.config_entries.async_update_entry(entry, options={CONF_FAVORITE_POSITION: 40})
    await hass.async_block_till_done()

    assert _button_id(hass, entry, "favorite") is not None

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_mark_buttons_recalibrate_without_transmitting(
    hass: HomeAssistant,
) -> None:
    """Mark open/closed move the estimate only — no RF frame is sent."""
    calls: list[dict] = []

    @callback
    def _record(call) -> None:
        calls.append(dict(call.data))

    hass.services.async_register("esphome", GATEWAY_SERVICE, _record)

    entry = _make_entry()
    await _setup_entry(hass, entry)

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": _button_id(hass, entry, "mark_open")},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert hass.states.get(COVER_ENTITY_ID).attributes["current_position"] == 100

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": _button_id(hass, entry, "mark_closed")},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert hass.states.get(COVER_ENTITY_ID).attributes["current_position"] == 0

    # The whole point of these buttons: the shutter never moved.
    assert calls == []

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_favorite_button_drives_the_cover(hass: HomeAssistant) -> None:
    """Pressing the favorite button sends the cover towards that position."""
    calls: list[dict] = []

    @callback
    def _record(call) -> None:
        calls.append(dict(call.data))

    hass.services.async_register("esphome", GATEWAY_SERVICE, _record)

    entry = _make_entry(**{CONF_FAVORITE_POSITION: 40})
    await _setup_entry(hass, entry)

    # Start from a known position so the direction is deterministic.
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": _button_id(hass, entry, "mark_open")},
        blocking=True,
    )
    await hass.async_block_till_done()
    calls.clear()

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": _button_id(hass, entry, "favorite")},
        blocking=True,
    )
    await hass.async_block_till_done()

    # 100 -> 40 is downwards: button code 3.
    assert [c["btn"] for c in calls] == [3]
    assert hass.states.get(COVER_ENTITY_ID).state == "closing"

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_calibration_button_transmits_and_starts_moving(
    hass: HomeAssistant,
) -> None:
    """Calibrate up sends UP and starts the timed measurement."""
    calls: list[dict] = []

    @callback
    def _record(call) -> None:
        calls.append(dict(call.data))

    hass.services.async_register("esphome", GATEWAY_SERVICE, _record)

    entry = _make_entry()
    await _setup_entry(hass, entry)

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": _button_id(hass, entry, "calibrate_up")},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert [c["btn"] for c in calls] == [1]
    assert hass.states.get(COVER_ENTITY_ID).state == "opening"

    assert await hass.config_entries.async_unload(entry.entry_id)
