"""Constantes pour l'intégration Dooya RF Covers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

DOMAIN: Final = "dooya"

# Repair issue raised when the configured ESPHome gateway service is missing.
ISSUE_GATEWAY_SERVICE_MISSING: Final = "esphome_service_missing"


def gateway_issue_id(entry_id: str) -> str:
    """Return the per-entry repair issue id for a missing gateway service."""
    return f"{ISSUE_GATEWAY_SERVICE_MISSING}_{entry_id}"


# The node YAML exposes one action per device: `esphome.<node>_transmit_dooya`.
TRANSMIT_SERVICE_SUFFIX: Final = "_transmit_dooya"


def transmit_service_name(esphome_device: str) -> str:
    """Return the ESPHome action name that transmits for this node.

    Config entries store the node slug with dashes (`volets-dooya-rf433`) while
    ESPHome registers its actions with underscores; derive the name in one
    place so the two spellings can never drift apart.
    """
    return f"{esphome_device.replace('-', '_')}{TRANSMIT_SERVICE_SUFFIX}"


def entry_value(entry: ConfigEntry, key: str, default: Any = None) -> Any:
    """Return a setting from a config entry, options winning over data.

    Every tunable starts life in `data` (written by the config flow) and may
    later be overridden in `options` — by the options flow, or by the
    calibration assistant writing back a measured travel time. Reading only one
    of the two silently ignores half the sources, so both are always consulted
    together through this helper.
    """
    return entry.options.get(key, entry.data.get(key, default))


EVENT_DOOYA_RECEIVED: Final = "esphome.dooya_received"

# Clés de configuration
CONF_ESPHOME_DEVICE: Final = "esphome_device"  # Nom du device ESPHome (slug)
CONF_DOOYA_ID: Final = "dooya_id"              # Identifiant 24 bits de la télécommande
CONF_CHANNEL: Final = "channel"                # Canal du volet (8 bits)
CONF_CHECK: Final = "check"                    # Code de contrôle (4 bits)
CONF_COVER_NAME: Final = "cover_name"          # Nom du volet
CONF_TRAVEL_TIME_UP: Final = "travel_time_up"  # Temps d'ouverture complet (s)
CONF_TRAVEL_TIME_DOWN: Final = "travel_time_down"  # Temps de fermeture complet (s)
CONF_REPEAT_COUNT: Final = "repeat_count"          # Nombre de répétitions de la trame RF (fiabilité)
CONF_FAVORITE_POSITION: Final = "favorite_position"  # Position favorite (0-100, optionnelle)

# Received frames matching one of our own transmissions (same button) less
# than this many seconds old are echoes picked up by another node, not a
# physical remote press. Covers repeat_count (max 3) x ~0.4 s per blocking
# transmit call plus event latency.
ECHO_SUPPRESS_WINDOW_SEC: Final = 2.0

# Calibration assistante : délai maximum entre le départ (UP/DOWN) et le
# STOP de l'utilisateur avant abandon de la mesure.
CALIBRATION_TIMEOUT_SEC: Final = 240.0

# Canal broadcast Dooya : les trames canal 0 sont exécutées par tous les
# volets appairés à la même télécommande (bouton "tous" des télécommandes
# multi-canaux).
BROADCAST_CHANNEL: Final = 0

# Le canal occupe 8 bits dans la trame (voir dooya_protocol : header + id 24
# bits + canal 8 bits + bouton 4 bits + check 4 bits). Les télécommandes
# courantes s'arrêtent à 16, mais rien dans l'encodage ne l'impose : des
# installations réelles utilisent des canaux bien au-delà (issue #18).
MAX_CHANNEL: Final = 255

# Valeurs par défaut
DEFAULT_CHANNEL: Final = 1
# No DEFAULT_CHECK_* here on purpose: the check nibble is derived from the
# button at transmit time (dooya_protocol.check_for_button), never defaulted.
DEFAULT_TRAVEL_TIME_UP: Final = 20.0
DEFAULT_TRAVEL_TIME_DOWN: Final = 20.0
DEFAULT_REPEAT_COUNT: Final = 1  # 1 = une seule émission (comportement par défaut)
