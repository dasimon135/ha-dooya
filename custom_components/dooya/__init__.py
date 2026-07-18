"""Intégration Dooya RF Covers pour Home Assistant."""

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

CARD_VERSION = "1.3.1"
CARD_URL = "/dooya_frontend/dooya-cover-card.js"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the bundled Lovelace card (served and auto-loaded by the frontend)."""
    try:
        await _async_register_card(hass)
    except Exception:  # pragma: no cover - card registration is best-effort
        _LOGGER.warning("Dooya: could not register the bundled card", exc_info=True)
    return True


async def _async_register_card(hass: HomeAssistant) -> None:
    """Serve the card file and add it as a frontend module."""
    from homeassistant.components import frontend
    from homeassistant.components.http import StaticPathConfig

    card_path = Path(__file__).parent / "frontend" / "dooya-cover-card.js"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(card_path), True)]
    )
    frontend.add_extra_js_url(hass, f"{CARD_URL}?v={CARD_VERSION}")


async def async_setup_entry(hass: HomeAssistant, entry: DooyaConfigEntry) -> bool:
    """Initialiser un config entry Dooya."""
    entry.runtime_data = DooyaRuntimeData()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Reload the entry when options change so the new ESPHome device,
    # travel times and repeat count apply without an HA restart.
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: DooyaConfigEntry) -> None:
    """Recharger l'entrée après un changement d'options."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: DooyaConfigEntry) -> bool:
    """Décharger un config entry Dooya."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        ir.async_delete_issue(hass, DOMAIN, gateway_issue_id(entry.entry_id))
    return unloaded
