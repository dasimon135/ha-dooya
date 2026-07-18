# ha-dooya — Copilot Instructions

## Context

HACS custom integration for Dooya RF433 roller shutters. Commands are
transmitted by one or more ESPHome nodes (ESP32 + CC1101) that expose a
`transmit_dooya` service to Home Assistant; the shutter position is
estimated from travel time (`assumed_state`, no feedback from the motor).

## Stack

- Python 3.13+ (Home Assistant 2026.5+)
- HA custom component (`custom_components/dooya/`)
- Dooya RF433 OOK protocol encoded/decoded in pure Python (`dooya_protocol.py`)
- Transmitter: ESPHome node(s) with CC1101; each node exposes
  `esphome.<node_slug>_transmit_dooya` and publishes the
  `esphome.dooya_received` event when a frame is sniffed

## Conventions

- Language: **English** for all public GitHub content (code, comments,
  commits, PRs, issues). French is only allowed in `translations/fr.json`.
- Python: snake_case, full type annotations, ruff (see `pyproject.toml`)
- 1 config entry = 1 shutter (or the channel-0 broadcast pseudo-shutter)
- Dooya timings (µs): Header 5000/1500 · Bit1 750/350 · Bit0 350/750
- Frame: header + 24-bit id + 8-bit channel + 4-bit button + 4-bit check
  (last bit = mark only)
- Buttons: UP=1, DOWN=3, STOP=5; check defaults to the button value
- Channel 0 is the broadcast channel ("all" button): no position estimate

## Structure

```
custom_components/dooya/
├── __init__.py          # setup/unload, DooyaRuntimeData, bundled card registration
├── manifest.json        # domain, version, no dependencies
├── const.py             # DOMAIN, CONF_*, defaults, repair issue ids
├── config_flow.py       # user (pick ESPHome node) → method → learn/manual → confirm; options; reconfigure
├── entity.py            # DooyaBaseEntity: device info, via_device, gateway availability tracking
├── cover.py             # DooyaCover: transmit via esphome.<node>_transmit_dooya, time-based position, calibration
├── button.py            # mark open/closed, calibrate up/down, favorite position
├── diagnostics.py       # config entry diagnostics (dooya_id redacted)
├── dooya_protocol.py    # encode_dooya, decode_dooya, DooyaData (pure Python)
├── echo_filter.py       # suppress RX echoes of our own transmissions (multi-node)
├── travel_calc.py       # pure position/travel-time math
├── device_match.py      # registry identifier helpers
├── frontend/            # bundled Lovelace card (auto-registered)
├── strings.json         # reference strings (EN)
└── translations/        # en.json, fr.json
```

## Transmit path

- `cover.py` resolves `esphome.<node_slug>_transmit_dooya` from the
  configured device slug (options override data) and calls it with
  `{dooya_id, channel, btn, check}`, repeated `repeat_count` times.
- A missing gateway/service raises a translated `HomeAssistantError` and
  creates a repair issue; no estimated motion starts if nothing was sent.
- Entity availability mirrors the gateway node's entities.

## Learn mode

- ESPHome publishes the `esphome.dooya_received` event when a Dooya frame
  is received: `{id: "00D1C917", channel: 5, button: 1, check: 1}`
- The config flow listens for this event for 30 s (step `learn`) using
  `async_show_progress` with a `progress_task`
- The same event keeps the position estimate in sync when the physical
  remote is used (with echo filtering for multi-node setups)

## Tests

- Pure-Python tests (protocol, echo filter, travel calc) run with plain
  pytest; HA-harness tests use `pytest-homeassistant-custom-component`
  and are skipped automatically when the harness is not installed.
