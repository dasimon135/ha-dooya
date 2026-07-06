"""Intégration Dooya RF Covers pour Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

PLATFORMS: list[Platform] = [Platform.COVER]


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
