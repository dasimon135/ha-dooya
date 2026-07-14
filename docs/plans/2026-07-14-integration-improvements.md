# Integration Improvements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add recalibration/favorite/calibration button entities, gateway-linked availability, broadcast channel 0, a travel-time calibration assistant, a diagnostics platform, pure-python position-math tests, and full FR/EN i18n.

**Architecture:** All features build on the existing single-cover-per-entry design. Position math is extracted into a pure module (`travel_calc.py`) so it is testable without Home Assistant. Button entities act on the cover object shared through `hass.data[DOMAIN][entry_id]`. Availability is derived from the state of the configured ESPHome gateway's entities (device/entity registry lookup). Base branch: `feat/integration-improvements` = card branch + `feat/multi-node-mesh` merged.

**Tech Stack:** Home Assistant custom integration (Python), plain pytest (no HA test harness available), vanilla-JS Lovelace card.

---

### Task 1: Extract pure position math (`travel_calc.py`) — TDD

- Create `custom_components/dooya/travel_calc.py`: `clamp_position()`, `position_after(start, direction, elapsed, travel_time, target)`, `travel_duration(distance, travel_time)`.
- Create `tests/test_travel_calc.py` first (failing), covering: mid-travel positions up/down, clamping at target, zero/None guards, duration maths.
- Refactor `cover.py::_refresh_position` and `_schedule_target_reached` to use it.
- Run `python -m pytest` (baseline 14 tests + new ones green).

### Task 2: Gateway-linked availability

- In `entity.py`: resolve the ESPHome gateway device via device registry (identifier domain `esphome`, slugified name == configured slug), collect its entity ids, `available` = not all of them `unavailable`. Subscribe to their state changes in `async_added_to_hass` (helper `async_track_state_change_event`).
- Fallback: gateway not resolvable → entity stays available (no regression).

### Task 3: Button platform (recalibration + favorite + calibration)

- Create `button.py`: `mark_open`, `mark_closed` (EntityCategory.CONFIG), `calibrate_up`, `calibrate_down` (CONFIG), `favorite` (only when the option is set). All use `translation_key` + `has_entity_name`.
- Cover registers itself in `hass.data[DOMAIN][entry_id]["cover"]` on add; buttons act through it.
- Add `Platform.BUTTON` to `PLATFORMS`.

### Task 4: Broadcast channel 0

- `config_flow.py` manual step: allow channel 0 (`Range(min=0)`), document "0 = all shutters".
- `cover.py`: channel 0 → no `SET_POSITION`, no position estimate, `is_closed = None`.
- `_handle_dooya_event`: a channel-0 frame (remote "all" button or HA broadcast entity) also drives every per-channel cover with the same remote id.

### Task 5: Favorite position

- `CONF_FAVORITE_POSITION` in options flow (optional, 0-100).
- `favorite` button → `set_cover_position(favorite)`.
- Card: show a star preset chip when a favorite sibling button exists.

### Task 6: Travel-time calibration assistant

- `cover.async_start_calibration(direction)`: from the matching end stop, send UP/DOWN and record `t0`; the next STOP (HA button, service, or physical remote frame) measures elapsed time, persists it in the entry options (`async_update_entry` → auto reload), finalizes position, and raises a persistent notification with the measured value. 240 s timeout cancels silently.

### Task 7: Diagnostics platform

- Create `diagnostics.py`: dump entry data + options with `dooya_id` redacted.

### Task 8: i18n

- Move service names/descriptions out of `services.yaml` into `strings.json` (`services` section) with `translations/en.json` + `fr.json`.
- Add `entity.button.*` names (EN source, FR translation) for all new buttons.
- Add new option/config-flow strings (channel 0 hint, favorite position).

### Task 9: Version, docs, checks

- Bump manifest to 0.6.0; README sections (new entities, broadcast, calibration assistant, diagnostics).
- `python -m pytest`, `python -m py_compile`, `node --check` on the card.
- One commit per task above.
