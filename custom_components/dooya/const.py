"""Constantes pour l'intégration Dooya RF Covers."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "dooya"

# Ancien événement historique, conservé pour compatibilité documentaire.
EVENT_DOOYA_TRANSMIT: Final = "dooya.transmit"
EVENT_DOOYA_RECEIVED: Final = "esphome.dooya_received"

# Clés de configuration
CONF_ESPHOME_DEVICE: Final = "esphome_device"  # Nom du device ESPHome (slug)
CONF_DOOYA_ID: Final = "dooya_id"              # Identifiant 24 bits de la télécommande
CONF_CHANNEL: Final = "channel"                # Canal du volet (1-16)
CONF_CHECK: Final = "check"                    # Code de contrôle (4 bits)
CONF_COVER_NAME: Final = "cover_name"          # Nom du volet
CONF_TRAVEL_TIME_UP: Final = "travel_time_up"  # Temps d'ouverture complet (s)
CONF_TRAVEL_TIME_DOWN: Final = "travel_time_down"  # Temps de fermeture complet (s)
CONF_REPEAT_COUNT: Final = "repeat_count"          # Nombre de répétitions de la trame RF (fiabilité)

# Received frames matching one of our own transmissions (same button) less
# than this many seconds old are echoes picked up by another node, not a
# physical remote press. Covers repeat_count (max 3) x ~0.4 s per blocking
# transmit call plus event latency.
ECHO_SUPPRESS_WINDOW_SEC: Final = 2.0

# Valeurs par défaut
DEFAULT_CHANNEL: Final = 1
DEFAULT_CHECK_UP: Final = 1
DEFAULT_CHECK_DOWN: Final = 3
DEFAULT_CHECK_STOP: Final = 5
DEFAULT_TRAVEL_TIME_UP: Final = 20.0
DEFAULT_TRAVEL_TIME_DOWN: Final = 20.0
DEFAULT_REPEAT_COUNT: Final = 1  # 1 = une seule émission (comportement par défaut)
