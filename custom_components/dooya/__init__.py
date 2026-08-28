"""Dooya RF Covers integration for Home Assistant."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, issue_registry as ir
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .const import DOMAIN, gateway_issue_id

if TYPE_CHECKING:
    from .cover import DooyaCover

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [Platform.COVER, Platform.BUTTON]


@dataclass
class DooyaRuntimeData:
    """Runtime objects shared between the platforms of a config entry."""

    cover: DooyaCover | None = None


type DooyaConfigEntry = ConfigEntry[DooyaRuntimeData]

CARD_URL = "/dooya_frontend/dooya-cover-card.js"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the bundled Lovelace card (served and auto-loaded by the frontend)."""
    try:
        await _async_register_card(hass)
    except Exception:
        # The card is a convenience on top of a working integration: failing to
        # serve it must never stop the covers from being set up.
        _LOGGER.error(
            "Could not register the bundled Dooya card; the integration still "
            "works but 'custom:dooya-cover-card' will not be available",
            exc_info=True,
        )
    return True


async def _async_register_card(hass: HomeAssistant) -> None:
    """Serve the card file and add it as a frontend module.

    `http` is a hard dependency because `hass.http` is dereferenced here;
    `frontend` is only an after_dependency. The card is a convenience, and
    environments without the `hass_frontend` package (the HA test harness, for
    one) must still be able to set the integration up.
    """
    from homeassistant.components import frontend
    from homeassistant.components.http import StaticPathConfig

    card_path = Path(__file__).parent / "frontend" / "dooya-cover-card.js"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(card_path), True)]
    )
    # Cache-bust on the integration version rather than a hand-maintained
    # constant: a released update can never serve a stale card.
    integration = await async_get_integration(hass, DOMAIN)
    frontend.add_extra_js_url(hass, f"{CARD_URL}?v={integration.version}")


async def async_setup_entry(hass: HomeAssistant, entry: DooyaConfigEntry) -> bool:
    """Set up a Dooya config entry."""
    entry.runtime_data = DooyaRuntimeData()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Reload the entry when options change so the new ESPHome device,
    # travel times and repeat count apply without an HA restart.
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: DooyaConfigEntry) -> None:
    """Reload the entry after its options changed."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: DooyaConfigEntry) -> bool:
    """Unload a Dooya config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        ir.async_delete_issue(hass, DOMAIN, gateway_issue_id(entry.entry_id))
    return unloaded
