"""Diagnostics pour l'intégration Dooya RF Covers."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_DOOYA_ID, DOMAIN

# The remote id would let anyone replay frames to the shutters — redact it.
TO_REDACT = {CONF_DOOYA_ID}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Retourner les diagnostics d'une entrée de configuration."""
    cover = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("cover")
    cover_state: dict[str, Any] = {}
    if cover is not None:
        cover_state = {
            "current_position": cover.current_cover_position,
            "is_opening": cover.is_opening,
            "is_closing": cover.is_closing,
            "available": cover.available,
        }

    return {
        "entry": {
            "title": entry.title,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "cover": cover_state,
    }
