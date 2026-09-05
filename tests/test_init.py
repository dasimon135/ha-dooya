"""Tests for the Dooya integration setup and teardown (HA test harness).

Skipped automatically when pytest-homeassistant-custom-component is not
installed (e.g. on Windows, where the harness cannot run).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if sys.platform == "win32":
    pytest.skip(
        "the Home Assistant test harness does not run on Windows",
        allow_module_level=True,
    )
pytest.importorskip("pytest_homeassistant_custom_component")

import homeassistant.components
from homeassistant.components.lovelace.const import LOVELACE_DATA, MODE_YAML
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.dooya as dooya
from custom_components.dooya import (
    CARD_URL,
    _async_register_card,
    _async_register_resource,
    async_setup,
)
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


def _resources(hass: HomeAssistant) -> list[dict]:
    return list(hass.data[LOVELACE_DATA].resources.async_items())


async def _setup_card(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, "lovelace", {})
    assert await async_setup(hass, {})
    await hass.async_block_till_done()


def _ours(hass: HomeAssistant) -> list[dict]:
    return [item for item in _resources(hass) if item["url"].split("?")[0] == CARD_URL]


async def test_the_card_is_registered_as_a_lovelace_resource(
    hass: HomeAssistant,
) -> None:
    """Lovelace waits for its own resources; nothing waits for a module URL.

    Field report 2026-09-04, and independently ha-rf-fan#44 from another user:
    a card handed to the frontend's extra-module list renders as a
    configuration error in the Android companion app every time, and on about
    one hard reload in three in a desktop browser -- while the same card
    registered as a dashboard resource works every time. Reinstalling the app
    changes nothing, so this is not a cache: Lovelace loads its own resources
    and waits for them before rendering a card.
    """
    await _setup_card(hass)

    assert _ours(hass), f"the card was not registered: {_resources(hass)}"
    assert _ours(hass)[0]["type"] == "module"


async def test_it_is_registered_once_however_often_it_runs(
    hass: HomeAssistant,
) -> None:
    """Two copies race to define the same element and the loser is stuck.

    Registering again with the URL already in the store must adopt it, not
    append a second identical entry -- the defect ha-rf-fan#44 woke up to, one
    more copy per restart.
    """
    await _setup_card(hass)
    url = _ours(hass)[0]["url"]

    assert await _async_register_resource(hass, url)
    await hass.async_block_till_done()

    assert len(_ours(hass)) == 1


async def test_an_existing_registration_is_moved_to_the_current_url(
    hass: HomeAssistant,
) -> None:
    """A hand-added resource is adopted, not duplicated: it is the stale one."""
    assert await async_setup_component(hass, "lovelace", {})
    resources = hass.data[LOVELACE_DATA].resources
    await resources.async_get_info()
    await resources.async_create_item(
        {"res_type": "module", "url": f"{CARD_URL}?v=stale"}
    )

    assert await async_setup(hass, {})
    await hass.async_block_till_done()

    assert len(_ours(hass)) == 1
    assert _ours(hass)[0]["url"] != f"{CARD_URL}?v=stale"


async def test_the_card_url_carries_the_file_digest(hass: HomeAssistant) -> None:
    """``?v=`` moves with the file, so a shipped change is always a new URL.

    It used to be the integration version, which does not move when only the
    card changes -- a browser then keeps executing the copy it holds across an
    update. That is a cache-correctness fix, not the fix for the card going
    missing; see ``test_the_card_is_registered_as_a_lovelace_resource``.
    """
    await _setup_card(hass)

    card = Path(dooya.__file__).parent / "frontend" / "dooya-cover-card.js"
    digest = hashlib.sha256(card.read_bytes()).hexdigest()[:12]
    assert f"{CARD_URL}?v={digest}" in [item["url"] for item in _resources(hass)]


async def test_yaml_mode_falls_back_to_the_module_list(hass: HomeAssistant) -> None:
    """In YAML mode the resource list is the user's file, not ours to write."""
    assert await async_setup_component(hass, "lovelace", {})
    hass.data[LOVELACE_DATA].resource_mode = MODE_YAML
    # The harness has no `hass_frontend` package, so the component is not
    # loaded; the fallback declines to touch a module list that is not there.
    hass.config.components.add("frontend")

    frontend = MagicMock()
    http = MagicMock(async_register_static_paths=AsyncMock())
    with (
        patch.dict(sys.modules, {"homeassistant.components.frontend": frontend}),
        patch.object(homeassistant.components, "frontend", frontend, create=True),
        patch.object(hass, "http", http, create=True),
    ):
        await _async_register_card(hass)

    frontend.add_extra_js_url.assert_called_once()
    assert frontend.add_extra_js_url.call_args[0][1].split("?")[0] == CARD_URL


async def test_reload_applies_new_travel_times(hass: HomeAssistant) -> None:
    """Editing the options reloads the entry instead of needing a restart."""
    entry = _make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    hass.config_entries.async_update_entry(entry, options={CONF_TRAVEL_TIME_UP: 33.0})
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    # The reloaded cover reads the option, which now wins over entry data.
    assert entry.runtime_data.cover._travel_time_up == 33.0

    assert await hass.config_entries.async_unload(entry.entry_id)
