# ha-dooya — Copilot Instructions

## Context

HACS custom integration for Dooya RF433 roller shutters. Commands are
transmitted by one or more ESPHome nodes (ESP32 + CC1101) that expose a
`transmit_dooya` service to Home Assistant; the shutter position is
estimated from travel time (`assumed_state`, no feedback from the motor).

## Stack

- Python 3.13+ (Home Assistant 2026.5+)
- HA custom component (`custom_components/dooya/`)
- Transmitter: ESPHome node(s) with CC1101; each node exposes
  `esphome.<node_slug>_transmit_dooya` and publishes the
  `esphome.dooya_received` event when a frame is sniffed
- **Frames are encoded and decoded on the ESP32 by ESPHome's own C++
  `DooyaProtocol`, not here.** This integration only passes it the four field
  values. `dooya_protocol.py` is a reference implementation kept so the unit
  tests can pin the timing table the ESPHome side must agree with — editing it
  has zero effect on what the hardware transmits. Mistaking it for the transmit
  path is what let a dead config field survive unnoticed (see
  `docs/plans/2026-07-26-debug-audit.md` §1.1).

## Conventions

- Language: **English** for all public GitHub content (code, comments,
  commits, PRs, issues). French is only allowed in `translations/fr.json`.
- Python: snake_case, full type annotations, ruff (see `pyproject.toml`)
- 1 config entry = 1 shutter (or the channel-0 broadcast pseudo-shutter)
- Dooya timings (µs): Header 5000/1500 · Bit1 750/350 · Bit0 350/750
- Frame: header + 24-bit id + 8-bit channel + 4-bit button + 4-bit check
  (last bit = mark only)
- Buttons: UP=1, DOWN=3, STOP=5. The check nibble **always repeats the button
  code** and is derived at transmit time (`dooya_protocol.check_for_button`) —
  it is deliberately NOT configurable. The learn step only ever observes the
  check of an UP press, so a single stored value cannot be correct for UP, DOWN
  and STOP at once. Do not re-add a per-entry check override.
- `dooya_id` is 24 bits: validate against `MAX_DOOYA_ID` and format as `:06X`.
  A wider value is silently truncated by the encoder on the ESP32, so the node
  would transmit a different remote id than the UI shows.
- Channel 0 is the broadcast channel ("all" button): no position estimate.
  A shutter identity is `id + channel`, so channel 0 legitimately coexists with
  the per-channel entries of the same remote — never key uniqueness on id alone.

## Structure

```
custom_components/dooya/
├── __init__.py          # setup/unload, DooyaRuntimeData, bundled card registration
├── manifest.json        # dependencies: ["http"], after_dependencies: ["frontend"]
├── const.py             # DOMAIN, CONF_*, defaults, repair issue ids
├── config_flow.py       # user (pick ESPHome node) → method → learn/manual → confirm; options; reconfigure; unique_id + 24-bit id guards
├── entity.py            # DooyaBaseEntity: device info, via_device, gateway availability tracking
├── cover.py             # DooyaCover: transmit via esphome.<node>_transmit_dooya, time-based position, calibration
├── button.py            # mark open/closed, calibrate up/down, favorite position
├── diagnostics.py       # config entry diagnostics (dooya_id redacted)
├── dooya_protocol.py    # DooyaData, buttons, check_for_button, MAX_DOOYA_ID + reference encode/decode (NOT the transmit path)
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
  `{dooya_id, channel, btn, check}`, repeated `repeat_count` times. `check` is
  derived from `btn`, never read from the config entry.
- `repeat_count` stacks on top of ESPHome: `dooya-node.yaml` already does
  `set_send_times(5)`, so `repeat_count: 2` means 10 frames per command.
- A missing gateway/service raises a translated `HomeAssistantError` and
  creates a repair issue; no estimated motion starts if nothing was sent.
- Entity availability mirrors the gateway node's entities.
- `_refresh_position()` is pure on purpose: it updates `_current_position` and
  nothing else. HA reads `is_closed` / `is_opening` / `is_closing` /
  `current_cover_position` *while* building a state object, so ending a
  movement from there re-enters `async_write_ha_state`, and cancelling timers
  from there lets a plain state read drop the pending STOP of a partial move.
  Ending a movement belongs to the timer callbacks that own it.

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
- The harness cannot run on Windows (`ModuleNotFoundError: fcntl`). Run it in a
  Linux container with the repo mounted at `/app`.
- **Never use freezegun for the motion tests.** `_refresh_position()` reads
  `time.monotonic()` while `async_call_later` uses the event-loop clock; a
  frozen clock desynchronises the two and fabricates off-by-a-few position
  failures that look like product bugs but are pure artefacts. Use short real
  travel times (2–3 s in the entry data) plus real `asyncio.sleep`, as
  `tests/test_cover_motion.py` does.
- `pytest-homeassistant-custom-component` does **not** ship the
  `home-assistant-frontend` wheel, so `frontend` can never be a hard
  `dependency` — setup dies with `No module named 'hass_frontend'`. A local
  container may have that wheel and pass anyway; reproduce CI with
  `pip uninstall -y home-assistant-frontend` before trusting a green run.
