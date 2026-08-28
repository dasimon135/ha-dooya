"""Tests for the Dooya integration setup and teardown (HA test harness).

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

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dooya import async_setup
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
COVER_ENTITY_ID = "cover.salon"


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
            CONF_CHECK: 7,
            CONF_COVER_NAME: "Salon",
            CONF_TRAVEL_TIME_UP: 20.0,
            CONF_TRAVEL_TIME_DOWN: 18.0,
        },
    )


async def test_setup_loads_both_platforms(hass: HomeAssistant) -> None:
    """A loaded entry exposes its cover and its recalibration buttons."""
    entry = _make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(COVER_ENTITY_ID) is not None

    registry = er.async_get(hass)
    domains = {
        e.domain for e in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    assert domains == {"cover", "button"}

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_unload_releases_the_cover(hass: HomeAssistant) -> None:
    """Unloading tears the entity down and drops the shared cover reference.

    The button platform reaches the cover through `runtime_data`; a stale
    reference after unload would let a button press drive a dead entity.
    """
    entry = _make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Home Assistant drops `runtime_data` from the entry on unload, so hold the
    # shared object itself to observe what the entity did to it on the way out.
    runtime_data = entry.runtime_data
    assert runtime_data.cover is not None

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    assert runtime_data.cover is None
    # Home Assistant keeps a restored placeholder state for an unloaded entry
    # rather than dropping it, so the check is on availability, not absence.
    assert hass.states.get(COVER_ENTITY_ID).state == "unavailable"


async def test_setup_survives_a_failing_card_registration(
    hass: HomeAssistant,
) -> None:
    """`async_setup` never fails because of the bundled Lovelace card.

    The card is a convenience on top of a working integration. In the test
    harness the frontend package is absent, which is exactly the situation the
    broad except in `async_setup` exists for: it must log and carry on.
    """
    assert await async_setup(hass, {}) is True


async def test_reload_applies_new_travel_times(hass: HomeAssistant) -> None:
    """Editing the options reloads the entry instead of needing a restart."""
    entry = _make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    hass.config_entries.async_update_entry(
        entry, options={CONF_TRAVEL_TIME_UP: 33.0}
    )
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    # The reloaded cover reads the option, which now wins over entry data.
    assert entry.runtime_data.cover._travel_time_up == 33.0

    assert await hass.config_entries.async_unload(entry.entry_id)
