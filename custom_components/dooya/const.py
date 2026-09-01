"""Constants for the Dooya RF Covers integration."""

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

# Configuration keys
CONF_ESPHOME_DEVICE: Final = "esphome_device"  # ESPHome device name (slug)
CONF_DOOYA_ID: Final = "dooya_id"  # 24-bit remote identifier
CONF_CHANNEL: Final = "channel"  # Shutter channel (8 bits)
CONF_CHECK: Final = "check"  # Check nibble (4 bits)
CONF_COVER_NAME: Final = "cover_name"  # Shutter name
CONF_IS_GROUP: Final = "is_group"  # This cover is the remote's common button
CONF_TRAVEL_TIME_UP: Final = "travel_time_up"  # Full opening time (s)
CONF_TRAVEL_TIME_DOWN: Final = "travel_time_down"  # Full closing time (s)
CONF_REPEAT_COUNT: Final = "repeat_count"  # RF frame repetitions (reliability)
CONF_FAVORITE_POSITION: Final = (
    "favorite_position"  # Favorite position (0-100, optional)
)

# Received frames matching one of our own transmissions (same button) less
# than this many seconds old are echoes picked up by another node, not a
# physical remote press. Covers repeat_count (max 3) x ~0.4 s per blocking
# transmit call plus event latency.
ECHO_SUPPRESS_WINDOW_SEC: Final = 2.0

# Calibration assistant: longest gap allowed between the start (UP/DOWN) and
# the user's STOP before the measurement is abandoned.
CALIBRATION_TIMEOUT_SEC: Final = 240.0

# Dooya broadcast channel: on most remotes, channel 0 frames are executed by
# every shutter paired with the same remote (the "all" button).
#
# It is only the *default*, not a rule. Some motors ignore channel 0 entirely
# and answer a group button on a channel of its own (issue #33: a remote whose
# "all" button transmits on channel 80). The group role is therefore declared
# by CONF_IS_GROUP on one cover rather than inferred from the channel number,
# and this value is what that flag defaults to — so entries created before the
# flag existed keep behaving exactly as they did, with no migration.
BROADCAST_CHANNEL: Final = 0

# The channel occupies 8 bits of the frame (see dooya_protocol: header +
# 24-bit id + 8-bit channel + 4-bit button + 4-bit check). Common remotes stop
# at 16, but nothing in the encoding requires that: real installations use
# channels well beyond it (issue #18).
MAX_CHANNEL: Final = 255

# Defaults
DEFAULT_CHANNEL: Final = 1
# No DEFAULT_CHECK_* here on purpose: the check nibble is derived from the
# button at transmit time (dooya_protocol.check_for_button), never defaulted.
DEFAULT_TRAVEL_TIME_UP: Final = 20.0
DEFAULT_TRAVEL_TIME_DOWN: Final = 20.0
DEFAULT_REPEAT_COUNT: Final = 1  # 1 = a single transmission (default behaviour)
