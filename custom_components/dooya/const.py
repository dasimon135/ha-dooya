"""Constantes pour l'intégration Dooya RF Covers."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "dooya"

# Ancien événement historique, conservé pour compatibilité documentaire.
EVENT_DOOYA_TRANSMIT: Final = "dooya.transmit"

# Clés de configuration
CONF_ESPHOME_DEVICE: Final = "esphome_device"  # Nom du device ESPHome (slug)
CONF_DOOYA_ID: Final = "dooya_id"              # Identifiant 24 bits de la télécommande
CONF_CHANNEL: Final = "channel"                # Canal du volet (1-16)
CONF_CHECK: Final = "check"                    # Code de contrôle (4 bits)
CONF_COVER_NAME: Final = "cover_name"          # Nom du volet

# Valeurs par défaut
DEFAULT_CHANNEL: Final = 1
DEFAULT_CHECK_UP: Final = 1
DEFAULT_CHECK_DOWN: Final = 3
DEFAULT_CHECK_STOP: Final = 5
