# v0.12.1 Review Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the six defects the 2026-09-23 review found in v0.12.0.

**Architecture:** Independent fixes, one commit each, each with a test that fails first. Worktree `C:/Users/dasim/repos/homeassistant/_wt/dooya-fixes`, branch `fix/review-2026-09-23`, from `origin/main` 5cf9575 (v0.12.0).

**Tech Stack:** Home Assistant custom integration (Python), Lovelace card (plain JS, tested under Node through `tests/card_harness.js`), an automation blueprint (YAML).

---

## Ground rules

- Work only in this worktree. The main checkout is shared with other sessions; a second worktree, `_wt/dooya-repeater`, belongs to another feature.
- Home Assistant harness tests only run in docker:

  ```bash
  MSYS_NO_PATHCONV=1 docker run --rm -v "C:/Users/dasim/repos/homeassistant/_wt/dooya-fixes:/app" -w /app dooya-tests:latest sh -c "pip uninstall -y home-assistant-frontend >/dev/null 2>&1; python -m pytest -q -p no:cacheprovider <ARGS>"
  ```

  Called `DOCKER_PYTEST` below. The image has no Node, so card tests are skipped there; run them on the host: `python -m pytest tests/test_card_*.py -q` (Node is installed on the host). Pure tests: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest <file> -q`.
- Lint: `python -m ruff format <touched files> && python -m ruff check . && python -m ruff format --check .` (CI runs `ruff format --check` on the whole repo, Markdown code blocks included).
- Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. No em dash anywhere. Public text in English, except `translations/fr.json`.
- Baseline: `DOCKER_PYTEST` gives 160 passed, 28 skipped.

---

### Task 1: `_finalize_position` cancels the timers first

**Defect.** `_finalize_position` sets `_current_position`, then `_stop_estimated_motion()` cancels the travel timers. With asyncio debug on (Home Assistant's `debug: true`, and the test harness), `asyncio.Handle.cancel()` calls `repr()` on the handle; that reaches `Entity.__repr__`, which reads the state, which runs `_refresh_position()` while the direction is still set, and overwrites the position just set. `mark_closed`, `mark_open` and `set_known_position` during a movement are undone.

**Test first** (`tests/test_cover_motion.py`): open a cover from 0 (`TRAVEL = 3.0`), wait about 1 s, call `dooya.mark_closed`; assert state `closed` and `current_position == 0`. It must fail on the current code (the position comes back near 33).

**Fix:** first line of `_finalize_position`: `self._cancel_motion_callbacks()`, with a one-line comment saying why (the debug repr of a cancelled timer reads the state).

**Commit:** `fix(cover): mark open or closed holds during a movement`.

---

### Task 2: a movement in progress survives a restart or a reload

**Defects.**
- Home Assistant does not unload config entries when it stops (`ConfigEntry.async_shutdown` only cancels setup retries), so a partial move's pending STOP dies with the process and the shutter runs to its end stop. The ESPHome connection is only closed at `EVENT_HOMEASSISTANT_CLOSE`, after `EVENT_HOMEASSISTANT_STOP` and `EVENT_HOMEASSISTANT_FINAL_WRITE`, so a STOP can still be transmitted on `EVENT_HOMEASSISTANT_STOP`, and the state written then is what restore saves.
- Reloading an entry during a full travel (to 0 or 100) keeps the mid-travel position: no STOP is due, the motor reaches its end stop, but the estimate is frozen where it was.

**Fix, in `cover.py`.** Generalise `async_stop_pending_partial_move` (it is called from `__init__.async_unload_entry` and from `async_will_remove_from_hass`) into `async_settle_movement`:
- a partial move pending: as today, transmit STOP and stop the estimate where it is;
- a full travel in progress (target 0 or 100, direction set): transmit nothing, finalise the estimate at the target, since the motor goes there by itself;
- nothing moving: nothing.

In `async_added_to_hass`, register `self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, ...)` that calls it, and unsubscribe on removal (`self.async_on_remove`). Keep the existing callers.

**Tests first:**
- `set_cover_position 50` on a cover at 0, then `hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)`: a STOP frame goes out (`[1, 5]`) before the target time, and the state is stopped short of 50.
- `open_cover` from 0, reload the entry 1 s in: no STOP frame, and the restored cover is at 100, not about 33.

**Commit:** `fix(cover): settle a movement on restart and on reload`.

---

### Task 3: a position command to the current estimate is not a no-op

**Defect.** `async_set_cover_position` returns when the target equals the estimate. Two consequences: during a movement, asking for the position being passed does not stop the shutter; and the card's Open and Closed presets (they call `set_cover_position` 100 and 0) cannot resynchronise a shutter whose estimate drifted, the most natural gesture for it.

**Fix, in `async_set_cover_position`,** when `current_position == position`:
- moving: stop here (`await self.async_stop_cover()`);
- at rest and the target is 0 or 100: send the full command anyway (`async_close_cover` / `async_open_cover`, which already handle awnings); the motor goes to its end stop and the estimate is resynchronised;
- at rest at an intermediate position: nothing, as today.

**Tests first:**
- a cover estimated at 100 and at rest: `set_cover_position 100` transmits UP (it transmits nothing today);
- a cover opening from 0: `set_cover_position` to the current estimate transmits STOP.

**Commit:** `fix(cover): a position command to the current estimate still acts`.

---

### Task 4: the group cover has no position buttons

**Defect.** `button.py` creates Set as open, Set as closed, both calibration buttons, Toggle LED, and the favorite, for every entry. On the cover holding the group role they only log a warning, and the README (Broadcast Channel section) says the flagged cover drops its calibration.

**Fix.** Add `is_group_entry(entry) -> bool` to `const.py`, next to `entry_value`, with the existing rule (`entry_value(entry, CONF_IS_GROUP, entry.data.get(CONF_CHANNEL) == BROADCAST_CHANNEL)`), and use it in `cover.py` (where `_is_broadcast` is computed) and in `button.py`. In `button.py`, a group entry gets no buttons, and the button registry entries a previous version created for it are removed (`entity_registry.async_remove` for this entry's button unique ids), so they do not linger as unavailable.

**Tests first** (`tests/test_button.py`): a channel-0 entry and a flagged-group entry get no button entities; a stale button registry entry for a group entry is removed at setup.

**Commit:** `fix(button): the group cover has no position buttons`.

---

### Task 5: the card follows availability and supported features

**Defect.** `frontend/dooya-cover-card.js` never reads `unavailable` or `supported_features`. An unavailable cover is drawn as open with live controls; the group cover shows a slider and presets whose calls fail, since it does not support `SET_POSITION` (bit 4).

**Fix.** When the state is `unavailable`: show it as unavailable (the label the card already uses for unknown states, or Home Assistant's), and disable every control. When `supported_features & 4` is 0: no slider, no position presets, no position tap on the drawing; open, stop and close stay.

**Tests first**, with the Node harness (see `tests/test_card_layout.py` for how a scenario is built): an unavailable entity renders disabled controls; an entity without `SET_POSITION` renders no slider and no presets.

**Commit:** `fix(card): follow availability and the cover's supported features`.

---

### Task 6: the sun blueprint opens even when the sun rises before the earliest time

**Defect.** In `blueprints/automation/dooya/shutters_sun.yaml`, the morning branch only fires when the sun crosses `morning_elevation`, then requires `after: earliest_open`. If the crossing happens before that time, nothing fires later and the shutters stay closed all day, every day, for months in summer.

**Fix.** Add a `time` trigger at `earliest_open`, also with `id: morning`, and to the morning branch a `numeric_state` condition on `sun.sun` `elevation` `above: morning_elevation`. Crossing after the earliest time: both hold. Crossing before it: the time trigger opens at the earliest time. Winter, sun up after the earliest time: the time trigger fails the elevation condition, the crossing opens later.

**Test first:** a pure test (`tests/test_blueprint.py`) that loads the YAML with a loader accepting `!input`, and asserts the morning branch has both triggers and the elevation condition. State in the commit that the blueprint is not exercised in a running Home Assistant by this test.

**Commit:** `fix(blueprint): open in the morning even when the sun rises early`.

---

### Task 7: full suite, pull request, validation on the real Home Assistant, release v0.12.1

Full suite in docker plus the card tests on the host. Push, PR, CI green. Validate on the real Home Assistant with a phantom cover (id `FFFFFE`, channel 200): mark closed during a movement; set position to the current estimate; restart during a partial move and check the STOP line in the log; the group cover's buttons gone. Then merge, bump `manifest.json` to 0.12.1, and release through the `/release` skill with the maintainer's go (a patch: no forum post).
