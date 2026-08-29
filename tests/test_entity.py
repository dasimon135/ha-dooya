"""Tests for the shared Dooya entity base (requires the HA test harness).

Covers the two behaviours `DooyaBaseEntity` adds on top of a plain entity:
availability mirroring the ESPHome gateway, and the `via_device` link that
puts the shutter under its node in the device tree.

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
from homeassistant.helpers import device_registry as dr, entity_registry as er
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
)

GATEWAY_SLUG = "volets-dooya-rf433"
GATEWAY_IDENTIFIER = ("esphome", "a1b2c3d4")
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


def _create_gateway(hass: HomeAssistant) -> tuple[dr.DeviceEntry, str]:
    """Register an ESPHome device named like the configured node.

    The integration matches the gateway on the *slugified device name*, not on
    an identifier, because the config entry only ever stores the node slug.
    """
    esphome_entry = MockConfigEntry(domain="esphome", title="Node")
    esphome_entry.add_to_hass(hass)

    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=esphome_entry.entry_id,
        identifiers={GATEWAY_IDENTIFIER},
        name=GATEWAY_SLUG,
    )
    gateway_entity = er.async_get(hass).async_get_or_create(
        "sensor",
        "esphome",
        "gateway_uptime",
        device_id=device.id,
        config_entry=esphome_entry,
    )
    hass.states.async_set(gateway_entity.entity_id, "1234")
    return device, gateway_entity.entity_id


async def _setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_available_when_gateway_is_unknown(hass: HomeAssistant) -> None:
    """An unresolvable gateway must not make the shutter unavailable.

    Availability tracking is an enhancement; when no matching ESPHome device is
    in the registry the entity stays available rather than regressing to
    permanently unavailable.
    """
    entry = _make_entry()
    await _setup_entry(hass, entry)

    assert hass.states.get(COVER_ENTITY_ID).state != "unavailable"

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_availability_follows_the_gateway(hass: HomeAssistant) -> None:
    """The shutter goes unavailable with its node and comes back with it."""
    _, gateway_entity_id = _create_gateway(hass)

    entry = _make_entry()
    await _setup_entry(hass, entry)

    assert hass.states.get(COVER_ENTITY_ID).state != "unavailable"

    hass.states.async_set(gateway_entity_id, "unavailable")
    await hass.async_block_till_done()
    assert hass.states.get(COVER_ENTITY_ID).state == "unavailable"

    hass.states.async_set(gateway_entity_id, "5678")
    await hass.async_block_till_done()
    assert hass.states.get(COVER_ENTITY_ID).state != "unavailable"

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_shutter_is_linked_to_its_gateway(hass: HomeAssistant) -> None:
    """The shutter device hangs off the ESPHome node via `via_device`."""
    gateway, _ = _create_gateway(hass)

    entry = _make_entry()
    await _setup_entry(hass, entry)

    device_registry = dr.async_get(hass)
    shutter = device_registry.async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert shutter is not None
    assert shutter.via_device_id == gateway.id

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_shutter_stands_alone_without_a_gateway(hass: HomeAssistant) -> None:
    """With no matching node the device is still created, just unlinked."""
    entry = _make_entry()
    await _setup_entry(hass, entry)

    shutter = dr.async_get(hass).async_get_device(
        identifiers={(DOMAIN, entry.entry_id)}
    )
    assert shutter is not None
    assert shutter.via_device_id is None
    assert shutter.name == "Salon"

    assert await hass.config_entries.async_unload(entry.entry_id)
