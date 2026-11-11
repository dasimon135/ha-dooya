"""Renaming an entity_id must not stop a shutter that is moving.

From Home Assistant 2026.11 on, a custom entity that does not define
`async_entity_id_changed` is removed and added again when its entity_id is
renamed. Removing a cover settles its movement, which sends the STOP of a
partial move right away, so the shutter stopped short of its target.
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

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import Entity
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dooya_rf.button import DooyaButtonBase
from custom_components.dooya_rf.const import (
    CONF_CHANNEL,
    CONF_CHECK,
    CONF_COVER_NAME,
    CONF_DOOYA_ID,
    CONF_ESPHOME_DEVICE,
    CONF_TRAVEL_TIME_DOWN,
    CONF_TRAVEL_TIME_UP,
    DOMAIN,
)
from custom_components.dooya_rf.cover import DooyaCover
from custom_components.dooya_rf.entity import DooyaBaseEntity

GATEWAY_SERVICE = "volets_dooya_rf433_transmit_dooya"
ENTITY_ID = "cover.salon"
RENAMED = "cover.salon_renamed"
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


def test_every_class_with_add_or_remove_hooks_opts_in() -> None:
    """Home Assistant only counts the hook on the class that has the hooks.

    `_entity_class_requires_readd` (2026.11) looks for the method in the
    `__dict__` of each custom class defining `async_added_to_hass` or
    `async_will_remove_from_hass`, or of a subclass of it. Inheriting it from
    a base class is not enough for DooyaCover, which defines both hooks.
    """
    for cls in (DooyaBaseEntity, DooyaCover):
        assert "async_entity_id_changed" in cls.__dict__, cls.__name__
    # The buttons add no hook of their own: the base class covers them.
    assert "async_added_to_hass" not in DooyaButtonBase.__dict__
    assert "async_will_remove_from_hass" not in DooyaButtonBase.__dict__


@pytest.mark.skipif(
    not hasattr(Entity, "async_entity_id_changed"),
    reason="entity_ids change in place from Home Assistant 2026.11",
)
async def test_renaming_a_moving_cover_does_not_stop_it(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """The STOP goes out at the target, not when the entity_id is renamed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Salon",
        data={
            CONF_ESPHOME_DEVICE: "volets-dooya-rf433",
            CONF_DOOYA_ID: 0xD1C917,
            CONF_CHANNEL: 5,
            CONF_CHECK: 1,
            CONF_COVER_NAME: "Salon",
            CONF_TRAVEL_TIME_UP: TRAVEL,
            CONF_TRAVEL_TIME_DOWN: TRAVEL,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    cover = entry.runtime_data.cover
    cover._current_position = 0

    await hass.services.async_call(
        "cover",
        "set_cover_position",
        {"entity_id": ENTITY_ID, "position": 50},
        blocking=True,
    )
    await asyncio.sleep(0.3)
    er.async_get(hass).async_update_entity(ENTITY_ID, new_entity_id=RENAMED)
    await hass.async_block_till_done()

    # Same object, still on its way, nothing but the UP sent.
    assert entry.runtime_data.cover is cover
    assert [f["btn"] for f in frames] == [1]
    assert hass.states.get(ENTITY_ID) is None
    assert hass.states.get(RENAMED).state == "opening"

    await asyncio.sleep(TRAVEL * 0.5 + 1.0)
    await hass.async_block_till_done()
    assert [f["btn"] for f in frames] == [1, 5]
    assert hass.states.get(RENAMED).attributes["current_position"] == 50
