# ha-dooya — Debug Audit & Improvement Backlog

Date: 2026-07-26 · Version audited: `0.7.0` · Baseline: 54/54 tests pass on HA 2026.7.2

Every "Confirmed" item below was reproduced against the real integration in a
Home Assistant test harness, not inferred from reading the code. Items marked
"Refuted" were suspected and disproved — recorded so they are not re-opened.

## Status

Fixed in `0.8.0` (branch `fix/audit-2026-07`): §1.1, §1.2, §1.3, §1.4, §3.1,
§3.2, §3.3, §3.4, §3.5, the untracked-task item of §3.6, and the §4 coverage
gaps (`tests/test_cover_motion.py`). Suite went from 54 to 77 tests.

Still open: §3.6 `device_info` registry scan and broadcast-entity UI feedback,
§5 committed container test runner, §6 the French/English docstring mix.

---

## 1. Confirmed defects

### 1.1 The configured `check` code never reaches the RF frame — HIGH

`entity.py:54` reads `CONF_CHECK` into `self._check`, and nothing ever reads it
back. `cover.py` always transmits the hardcoded `DEFAULT_CHECK_UP/DOWN/STOP`
(1/3/5) instead.

Reproduction — entry configured with `check: 7`, opening the cover:

```
transmitted frame: {'dooya_id': 13748503, 'channel': 5, 'btn': 1, 'check': 1}
```

Impact:

- The "Check code (0-15)" field in the manual setup step and in the reconfigure
  step is dead UI. The user can change it, save it, see it in diagnostics — and
  it changes nothing.
- Worse, the learn step (`config_flow.py:194`) reads the *real* `check` off the
  physical remote and stores it. A remote whose check byte differs from the
  button value is learned correctly and then transmitted wrong, so the shutter
  never responds and the failure looks like an RF range problem.

The existing test does not catch this because its fixture uses `check: 1`,
which coincides with `DEFAULT_CHECK_UP`.

Fix options:

1. Use the stored value: transmit `self._check` for every button. Simplest, but
   only correct if the protocol really uses one check code per remote.
2. Use the stored value as an override and keep the per-button defaults as the
   fallback when `check` was never learned.

Option 2 is safer: it preserves today's behaviour for existing entries while
honouring a learned check. Either way, add a regression test with
`check != button`, and drop the field from the UI if option 1 proves wrong.

### 1.2 The same shutter can be added twice — MEDIUM

`DooyaConfigFlow` never calls `async_set_unique_id()` / `_abort_if_unique_id_configured()`.

Reproduction — running the manual flow twice with identical `dooya_id` +
`channel` yields `create_entry` both times instead of `abort`.

Impact: two config entries, two `cover.*` entities, two devices for one physical
shutter. Both entities transmit, both run independent position estimates, and
each one's transmission is seen by the other as a physical-remote press. The
estimates then disagree permanently.

Fix: `await self.async_set_unique_id(f"{dooya_id:06X}_{channel}")` before
creating the entry, plus `self._abort_if_unique_id_configured()`. Apply the same
guard in `async_step_reconfigure` so an entry cannot be edited into a collision.
Note that channel 0 (broadcast) legitimately coexists with per-channel entries,
so keying on `id + channel` is correct — do not key on `id` alone.

### 1.3 `dooya_id` accepts values wider than 24 bits — MEDIUM

`config_flow.py:261` does `int(user_input[CONF_DOOYA_ID], 16)` with no range
check. The Dooya frame carries a 24-bit id.

Reproduction — entering `FFFFFFFFFF` (40 bits) is accepted and stored as
`1099511627775`. The ESPHome lambda then casts it to `uint32_t` and
`DooyaProtocol().encode()` keeps the low 24 bits, so the node transmits a
*different* remote id than the one shown in the UI and in diagnostics.

Fix: validate `0 <= dooya_id <= 0xFFFFFF` in both `async_step_manual` and
`async_step_reconfigure`, reusing the existing `invalid_dooya_id` error key.
While there, make the id formatting consistent: the code mixes `:08X`
(`config_flow.py:338`, `cover.py:418`) with a 24-bit value. `:06X` is the honest
width.

### 1.4 Entity properties write state as a side effect — LOW (latent)

`is_closed`, `current_cover_position`, `is_opening` and `is_closing` all call
`_refresh_position()`, which can call `_finalize_position()` →
`_stop_estimated_motion()` → `async_write_ha_state()`. Home Assistant reads
exactly those properties while building a state object, so a state write can
re-enter itself.

Reproduction — instrumenting `async_write_ha_state` and triggering one write on
an entity whose movement has logically completed gives a maximum nesting depth
of **2**.

No state corruption is observable today: the nested write and the outer write
converge on the same values (verified end to end — see §2). This is filed as a
latent risk, not a live bug. It also means `_cancel_motion_callbacks()` can run
from inside a property read, which is the kind of thing that turns into a real
bug the moment the timing changes.

Fix: make `_refresh_position()` pure — have it compute and store the position
only, and move the "movement finished" transition into the timer callbacks
(`_handle_progress_tick`, `_handle_target_reached`) which are the legitimate
places to write state.

---

## 2. Verified as correct (do not re-open)

These were suspected during the audit and disproved by reproduction:

| Suspicion | Verdict |
|---|---|
| Options flow wipes `esphome_device` when no node is online | **Refuted.** `config_flow.py:415` deliberately re-adds the current device to the selector, and `vol.Required(..., default=...)` refills the key. Options keep `esphome_device` after save. |
| Full open settles below 100 % | **Refuted.** Settles at exactly `open` / `100` / `moves_since_sync: 0`, one UP frame. An earlier 98 % reading was a freezegun artefact: `time.monotonic()` and the asyncio loop clock diverge under a frozen clock, which does not happen in production. |
| Partial move never sends STOP | **Refuted.** `set_position: 50` emits `[UP, STOP]` and settles at exactly 50. |
| A user STOP mid-move leaves the auto-STOP armed | **Refuted.** Frame sequence is `[UP, STOP]`, no second STOP after the original target time. |
| A broadcast (channel 0) transmit is echo-filtered by sibling covers | **Refuted.** Siblings correctly go to `opening`. |
| Physical-remote resync is broken | **Refuted.** An `esphome.dooya_received` UP event starts the estimate and tracks correctly (25 % after 5 s on a 20 s travel time). |
| `strings.json` has drifted from the translations | **Refuted.** `en` and `fr` are key-for-key identical to `strings.json`. |

---

## 3. Code health

### 3.1 `dooya_protocol.py` is dead weight in production

`encode_dooya()` and `decode_dooya()` (~150 of the file's 187 lines) are imported
by nothing except `tests/test_dooya_protocol.py`. All real encoding happens in
ESPHome's C++ `DooyaProtocol().encode()`, and all real decoding in its
`on_dooya` trigger. Only `DooyaData`, `BUTTON_UP/DOWN/STOP` are live.

This is a trap: the module reads like the transmit path, so a future fix applied
there would have no effect on the hardware (and §1.1 shows that trap is already
live). Either delete the encode/decode functions and keep the constants, or keep
them and state in the module docstring that they are a reference implementation
used to validate the ESPHome timings, not the transmit path.

### 3.2 Documentation and version drift

- `README.md:319` says `Current version: 0.4.0`; `manifest.json` says `0.7.0`.
- `CARD_VERSION` is duplicated in `__init__.py:37` and `frontend/dooya-cover-card.js:13`
  (both `1.3.1` today). They are kept in sync by hand; if they drift, the
  cache-busting query string stops matching the shipped card and users get a
  stale card with no signal that anything is wrong.

Fix: read the card version from `manifest.json` at setup, or add a CI check that
asserts the two constants match. The README version line is better deleted than
maintained — HACS already shows the released version.

### 3.3 The bundled card does not escape interpolated values

`dooya-cover-card.js` builds markup with template literals into `innerHTML`
(lines 156, 184, 204, 252) and interpolates `name` (from `friendly_name` or the
card config) and `this._config.entity` unescaped. There is no escaping helper in
the file.

This is not a remote-attacker path — the values come from the user's own config
— but a shutter named `Salon <b>A</b> & "B"` renders broken markup. Add a small
`_esc()` helper and apply it to every interpolated value that is not a literal.

### 3.4 `favorite` button discovery is locale-dependent

`_favoriteButton()` (line 130) finds the favorite button by regex-matching
`/favori/i` against the entity id, which only works because the EN and FR names
happen to share that prefix. Adding any third locale silently loses the button.

Fix: match on the entity's `translation_key` / unique-id suffix (`_favorite`),
which is locale-independent and already unique per entry (`button.py:58`).

### 3.5 `http` is an `after_dependency`, not a dependency

`async_setup()` calls `hass.http.async_register_static_paths(...)`, but
`manifest.json` lists `http` under `after_dependencies`, which does not guarantee
it is loaded. In the test harness this raises
`AttributeError: 'NoneType' object has no attribute 'async_register_static_paths'`
on every single test — swallowed by the broad `except Exception` at
`__init__.py:45`.

It works in production because `default_config` always loads `http`, but the
manifest states the wrong contract and the swallowed exception hides real
failures. Move `frontend` and `http` to `dependencies`, and narrow the except
clause so an unexpected failure is not silently downgraded to a warning.

### 3.6 Minor

- `_handle_partial_target_reached` fires `hass.async_create_task()` without
  keeping a reference. If the entity is removed while the STOP is in flight the
  task is neither tracked nor cancelled. Use `entry.async_create_task()`.
- `device_info` scans the entire device registry on every access
  (`entity.py:135`). Resolve the gateway once in `async_added_to_hass` and cache it.
- The broadcast (channel 0) entity stays in state `unknown` forever: it never
  reports `opening`/`closing`, so pressing its buttons gives no UI feedback.
  Consider a short synthetic `opening`/`closing` pulse for the travel duration.
- `manifest.json` declares neither `quality_scale` nor `loggers`.

---

## 4. Test coverage gaps

54 tests pass, but only 8 exercise the Home Assistant harness, and none cover the
riskiest code — the timing state machine. Untested today:

- the calibration assistant end to end (start → STOP → measured time saved to
  options → entry reload), its timeout path, and its out-of-range rejection;
- the partial-move auto-STOP, and the `HomeAssistantError` branch in
  `_async_complete_partial_move` that re-targets the end stop when STOP fails;
- `_handle_dooya_event`: physical-remote resync, echo suppression against our
  own transmission, and broadcast frames moving sibling covers;
- the broadcast channel-0 entity (no `SET_POSITION`, no position);
- state restore in `async_added_to_hass`, including `moves_since_sync`;
- the options flow, the button platform, and diagnostics redaction.

Note for anyone writing these: **do not use `freezegun` for the motion tests.**
`_refresh_position()` reads `time.monotonic()` while `async_call_later` uses the
event-loop clock; under a frozen clock the two diverge and produce off-by-a-few
positions that are pure artefacts. The reliable pattern is short real travel
times (2–3 s) in the entry data plus real `asyncio.sleep`, which is what
validated §2 above. Alternatively, inject the clock into the entity so tests can
drive it deterministically — that would be the better long-term fix.

## 5. Developer experience

The HA harness cannot run on Windows (`ModuleNotFoundError: No module named 'fcntl'`),
and `tests/test_cover.py` / `test_config_flow.py` skip themselves on `win32`. So
on the primary dev machine the harness tests are never executed locally and
only run in CI.

A container makes them runnable locally; the audit used exactly this:

```powershell
docker run --rm -v "<repo>:/app" -w /app <image> sh -c "python -m pytest tests/ -q"
```

Worth committing a small `Dockerfile.tests` (or a `scripts/test.ps1` wrapper) and
documenting it, so the platform-skip is a convenience rather than a wall. This
mirrors the `madoka-tests` image already used for `daikin_madoka`.

## 6. Language consistency

Repo policy is English for all public GitHub content except i18n locale files.
Docstrings and comments are currently a French/English mix: `const.py`,
`echo_filter.py`, `travel_calc.py`, `device_match.py` are English, while
`cover.py`, `config_flow.py`, `button.py`, `entity.py`, `__init__.py`,
`diagnostics.py` and `dooya_protocol.py` still contain French docstrings
(~60 occurrences, most of them in `cover.py`). `docs/post-hacf.md` and
`docs/tuto-hacf.md` are French end-user guides, which is intentional and fine.

---

## 7. Suggested order of work

1. §1.1 `check` code — user-visible, silently breaks unusual remotes.
2. §1.2 unique_id + §1.3 id range — both are config-flow guards, one PR.
3. §4 tests for the calibration assistant and the event handler, using the
   real-clock pattern.
4. §1.4 make `_refresh_position()` pure (do this *after* the tests in step 3
   exist, so the refactor is covered).
5. §3.2 version drift, §3.5 manifest dependencies, §3.3 card escaping.
6. §3.1 decide the fate of `dooya_protocol.py`; §5 container test runner;
   §6 language pass.
