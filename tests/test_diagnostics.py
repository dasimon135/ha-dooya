"""Tests for the Dooya config entry diagnostics (requires the HA test harness).

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

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dooya.const import (
    CONF_CHANNEL,
    CONF_CHECK,
    CONF_COVER_NAME,
    CONF_DOOYA_ID,
    CONF_ESPHOME_DEVICE,
    CONF_REPEAT_COUNT,
    CONF_TRAVEL_TIME_DOWN,
    CONF_TRAVEL_TIME_UP,
    DOMAIN,
)
from custom_components.dooya.diagnostics import (
    async_get_config_entry_diagnostics,
)

GATEWAY_SLUG = "volets-dooya-rf433"
DOOYA_ID = 0x00D1C917


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
            CONF_DOOYA_ID: DOOYA_ID,
            CONF_CHANNEL: 5,
            CONF_CHECK: 7,
            CONF_COVER_NAME: "Salon",
            CONF_TRAVEL_TIME_UP: 20.0,
            CONF_TRAVEL_TIME_DOWN: 18.0,
        },
        options={CONF_REPEAT_COUNT: 2},
    )


async def _setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_remote_id_is_redacted(hass: HomeAssistant) -> None:
    """The remote id never appears in diagnostics.

    Anyone holding the id and channel can replay frames to the shutters, so
    this redaction is a security guarantee, not cosmetics.
    """
    entry = _make_entry()
    await _setup_entry(hass, entry)

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["entry"]["data"][CONF_DOOYA_ID] != DOOYA_ID
    # Belt and braces: the raw value must not survive anywhere in the payload,
    # in any spelling a future field might use.
    dumped = repr(diagnostics)
    assert str(DOOYA_ID) not in dumped
    assert f"{DOOYA_ID:06X}" not in dumped
    assert f"{DOOYA_ID:06x}" not in dumped

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_non_secret_fields_are_kept(hass: HomeAssistant) -> None:
    """Redaction must not gut the payload: everything else stays readable."""
    entry = _make_entry()
    await _setup_entry(hass, entry)

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    data = diagnostics["entry"]["data"]
    assert diagnostics["entry"]["title"] == "Salon"
    assert data[CONF_CHANNEL] == 5
    assert data[CONF_ESPHOME_DEVICE] == GATEWAY_SLUG
    assert data[CONF_TRAVEL_TIME_UP] == 20.0
    # Options are reported separately from data, unredacted.
    assert diagnostics["entry"]["options"] == {CONF_REPEAT_COUNT: 2}

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_cover_state_is_reported(hass: HomeAssistant) -> None:
    """The live cover estimate is included while the entry is loaded."""
    entry = _make_entry()
    await _setup_entry(hass, entry)

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    cover = diagnostics["cover"]
    assert set(cover) == {
        "current_position",
        "is_opening",
        "is_closing",
        "available",
    }
    assert cover["is_opening"] is False
    assert cover["is_closing"] is False

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_cover_state_empty_when_entity_absent(hass: HomeAssistant) -> None:
    """Diagnostics still answer when no cover is registered on the entry.

    `runtime_data.cover` is None before the platform sets up and again after
    the entity is removed; diagnostics must degrade rather than raise.
    """
    from custom_components.dooya import DooyaRuntimeData

    entry = _make_entry()
    entry.add_to_hass(hass)
    entry.runtime_data = DooyaRuntimeData()

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["cover"] == {}
    assert diagnostics["entry"]["data"][CONF_DOOYA_ID] != DOOYA_ID
