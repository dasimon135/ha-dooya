"""Intégration Dooya RF Covers pour Home Assistant."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.COVER]

CARD_VERSION = "1.0.0"
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


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Initialiser un config entry Dooya."""
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Reload the entry when options change so the new ESPHome device,
    # travel times and repeat count apply without an HA restart.
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Recharger l'entrée après un changement d'options."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Décharger un config entry Dooya."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
