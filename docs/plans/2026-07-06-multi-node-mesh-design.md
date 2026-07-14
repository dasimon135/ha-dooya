# Multi-node RF mesh design

Date: 2026-07-06
Status: validated

## Problem

A single ESP32+CC1101 node cannot reliably cover a whole house: reinforced
concrete walls limit both TX range (commands missed by distant motors) and RX
range (physical remote presses missed, so the estimated position drifts).

## Target architecture

Deploy several identical full TX+RX nodes (ESP32 + CC1101, same firmware as
`volets-dooya-rf433`, unique device name each), roughly one per RF zone.

- **TX**: each cover entity is statically assigned to its nearest node. The
  config flow already stores the ESPHome device per entry; the options flow
  gains the same selector so a cover can be reassigned without re-creating it.
- **RX**: every node publishes the same `esphome.dooya_received` event. Cover
  entities already listen on the HA bus regardless of source. Duplicate events
  (one press heard by several nodes) are harmless: the resync handler is
  idempotent, and remotes already repeat each frame ~5 times today.

## The echo problem (must fix first)

A node in RX hears the frames *transmitted by another node*. Without
filtering, an HA-initiated `set_position(60)` breaks: HA transmits UP and
schedules a delayed STOP; the echoed UP comes back as a received event,
`_start_estimated_motion(1, 100)` cancels the scheduled STOP, and the shutter
runs to the hard limit.

**Fix (HA side, `cover.py`):** per-cover echo filter. `_async_transmit`
records `(button, monotonic())`; `_handle_dooya_event` drops a received frame
whose button matches one of our own transmissions less than
`ECHO_SUPPRESS_WINDOW_SEC` (2.0 s) old. Only the *same* button is suppressed,
so a genuine opposite-button press during the window still gets through.

Known accepted limitation: a genuine remote press of the same button within
2 s of an HA command is swallowed; the physical effect on the motor is nil
(same command), so only a rare position drift can result.

## Changes

1. `custom_components/dooya/echo_filter.py` — pure-Python `TxEchoFilter`
   (unit-tested without HA, like `dooya_protocol`).
2. `cover.py` — wire the filter into `_async_transmit` and
   `_handle_dooya_event`; `_resolve_service_name` reads the ESPHome device
   from options first, then data.
3. `config_flow.py` — options flow gains the ESPHome device selector (list of
   devices exposing `transmit_dooya`, current value kept even if offline).
4. `__init__.py` — register an update listener that reloads the entry when
   options change (also makes travel-time/repeat changes apply live).
5. `strings.json` + `translations/{en,fr}.json` — new options field.
6. `esphome/dooya-node.yaml` — parameterized full TX+RX node template
   (substitutions for name/friendly name), copy per zone.

## Out of scope

- Broadcast/simultaneous TX from all nodes (RF self-interference).
- TX failover (a successful service call does not prove RF delivery).
- HA-harness config-flow tests (would require adding
  `pytest-homeassistant-custom-component`; revisit later).
