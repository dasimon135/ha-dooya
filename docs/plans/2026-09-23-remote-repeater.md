# Remote Repeater Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** An opt-in option per cover that sends a press from the physical remote again, through that cover's ESPHome node, without ever repeating Home Assistant's own commands.

**Architecture:** One guard in `DooyaCover._handle_dooya_event`, placed after the existing consistency and echo checks, schedules `_async_transmit(button)` for UP, DOWN and STOP when the frame's channel is exactly the cover's own. The press is claimed synchronously in the cover's `TxEchoFilter`, so the rest of the remote's burst and the echo of the repeat are ignored. Design: `docs/plans/2026-09-23-remote-repeater-design.md`.

**Tech Stack:** Home Assistant custom integration (Python 3.13+), voluptuous options flow, pytest with `pytest-homeassistant-custom-component`.

---

## Ground rules for whoever executes this

- Work only in the worktree `C:/Users/dasim/repos/homeassistant/_wt/dooya-repeater`, branch `feat/remote-repeater`. The main checkout is shared with other sessions.
- The Home Assistant test harness does not run on Windows (`fcntl`). Run it in the Linux image:

  ```bash
  MSYS_NO_PATHCONV=1 docker run --rm -v "C:/Users/dasim/repos/homeassistant/_wt/dooya-repeater:/app" -w /app dooya-tests:latest sh -c "pip uninstall -y home-assistant-frontend >/dev/null 2>&1; python -m pytest -q -p no:cacheprovider <ARGS>"
  ```

  Called `DOCKER_PYTEST <ARGS>` below. The `pip uninstall` matters: CI has no frontend wheel.
- Pure tests (`tests/test_i18n_hygiene.py`, `tests/test_dooya_protocol.py`) run natively: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest <file> -q`.
- Lint before every commit: `python -m ruff check . && python -m ruff format --check .`
- Every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- No em dash in any text: code comments, strings, README, commits.
- Everything public is in English, except `translations/fr.json`.

Baseline before starting: `DOCKER_PYTEST` (no args) must report 160 passed, 28 skipped.

---

### Task 1: Let the motion tests build entries with options

**Files:**
- Modify: `tests/test_cover_motion.py` (`_make_entry`, `_make_group_entry`)

**Step 1: Give `_make_entry` an `options` argument**

Replace the function with:

```python
def _make_entry(channel: int = CHANNEL, options: dict | None = None) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Salon",
        data={
            CONF_ESPHOME_DEVICE: GATEWAY_SLUG,
            CONF_DOOYA_ID: DOOYA_ID,
            CONF_CHANNEL: channel,
            CONF_CHECK: 1,
            CONF_COVER_NAME: "Salon",
            CONF_TRAVEL_TIME_UP: TRAVEL,
            CONF_TRAVEL_TIME_DOWN: TRAVEL,
        },
        options=options or {},
    )
```

**Step 2: Give `_make_group_entry` the same argument**

```python
def _make_group_entry(
    *, flagged: bool, channel: int = GROUP_CHANNEL, options: dict | None = None
) -> MockConfigEntry:
    """A second cover of the same remote, standing for its common button."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="All shutters",
        data={
            CONF_ESPHOME_DEVICE: GATEWAY_SLUG,
            CONF_DOOYA_ID: DOOYA_ID,
            CONF_CHANNEL: channel,
            CONF_CHECK: 1,
            CONF_COVER_NAME: "All shutters",
            CONF_TRAVEL_TIME_UP: TRAVEL,
            CONF_TRAVEL_TIME_DOWN: TRAVEL,
        },
        options={**({CONF_IS_GROUP: True} if flagged else {}), **(options or {})},
    )
```

**Step 3: Confirm nothing changed**

Run: `DOCKER_PYTEST tests/test_cover_motion.py`
Expected: same count as before, all passing.

**Step 4: Commit**

```bash
git add tests/test_cover_motion.py
git commit -m "test: let the motion tests build entries with options"
```

---

### Task 2: A press is repeated once, with this cover's id and channel

**Files:**
- Modify: `custom_components/dooya/const.py` (after `CONF_REPEAT_COUNT`, line 59)
- Modify: `custom_components/dooya/cover.py` (const import, `__init__` near line 144, `_handle_dooya_event` after the echo check near line 679)
- Test: `tests/test_cover_motion.py` (new section at the end of the file)

**Step 1: Write the failing test**

Add `CONF_REPEAT_REMOTE` to the `custom_components.dooya.const` import at the top of `tests/test_cover_motion.py`, then append:

```python
# ---- repeating presses from the remote (issue #19) ----------------------

REPEAT = {CONF_REPEAT_REMOTE: True}


async def test_a_press_is_repeated_through_this_covers_node(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """With the option on, a press on the remote goes out once more."""
    entry = await _setup(hass, _make_entry(options=REPEAT))
    entry.runtime_data.cover._current_position = 0

    _fire_frame(hass, 1)
    await hass.async_block_till_done()

    assert frames == [{"dooya_id": DOOYA_ID, "channel": CHANNEL, "btn": 1, "check": 1}]
    # The press itself still moves the estimate, as it always has.
    assert hass.states.get(ENTITY_ID).state == "opening"
```

**Step 2: Run it to verify it fails**

Run: `DOCKER_PYTEST tests/test_cover_motion.py -k repeated_through`
Expected: FAIL, `ImportError: cannot import name 'CONF_REPEAT_REMOTE'`.

**Step 3: Add the option key**

In `const.py`, right after `CONF_REPEAT_COUNT`:

```python
CONF_REPEAT_REMOTE: Final = "repeat_remote"  # Send presses from the remote again
```

**Step 4: Read the option in the cover**

In `cover.py`, add `CONF_REPEAT_REMOTE` to the `from .const import (...)` list (alphabetical, after `CONF_REPEAT_COUNT`). In `DooyaCover.__init__`, after the `self._is_awning = ...` line:

```python
        # A weak remote reaches some shutters and not others. Repeating its
        # presses from Home Assistant is only safe here, where our own frames
        # are known: an automation cannot tell them apart (issue #19).
        self._repeat_remote = bool(entry_value(config_entry, CONF_REPEAT_REMOTE, False))
```

**Step 5: Add the guard and the repeat**

In `_handle_dooya_event`, right after the echo check's `return` and before `if (direction := self._direction_for(button)) > 0:`:

```python
        # Only the entry owning this exact id and channel repeats, so a press
        # goes out once: group siblings reach this point through the group
        # channel, which is not their own. The press is claimed right away,
        # so the rest of the remote's burst, a few ms later, is an echo.
        if (
            self._repeat_remote
            and event_channel == self._channel
            and button in (BUTTON_UP, BUTTON_DOWN, BUTTON_STOP)
        ):
            self._echo_filter.record_tx(button, monotonic())
            self._config_entry.async_create_task(
                self.hass, self._async_repeat(button), "dooya remote repeat"
            )
```

Add the method right after `_async_transmit`:

```python
    async def _async_repeat(self, button: int) -> None:
        """Send a press from the remote again, for a shutter it does not reach."""
        _LOGGER.debug(
            "%s: repeating a press from the remote (button=%d)",
            self._cover_name,
            button,
        )
        await self._async_transmit(button)
```

**Step 6: Run the test to verify it passes**

Run: `DOCKER_PYTEST tests/test_cover_motion.py -k repeated_through`
Expected: PASS.

**Step 7: Lint and commit**

```bash
python -m ruff check . && python -m ruff format .
git add custom_components/dooya/const.py custom_components/dooya/cover.py tests/test_cover_motion.py
git commit -m "feat(cover): repeat presses from the remote, as an option"
```

---

### Task 3: A burst from the remote gives one repeat

**Files:**
- Test: `tests/test_cover_motion.py`

**Step 1: Write the test**

```python
async def test_a_burst_from_the_remote_is_repeated_once(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """A remote sends each press several times; it goes out again only once."""
    entry = await _setup(hass, _make_entry(options=REPEAT))
    entry.runtime_data.cover._current_position = 0

    for _ in range(3):
        _fire_frame(hass, 1)
    await hass.async_block_till_done()

    assert [f["btn"] for f in frames] == [1]
```

**Step 2: Run it**

Run: `DOCKER_PYTEST tests/test_cover_motion.py -k burst_from_the_remote`
Expected: PASS. Listeners run synchronously inside `async_fire`, so all three copies are handled before the repeat task starts: only the synchronous `record_tx` in the guard can stop copies two and three.

**Step 3: Prove the test can fail**

Temporarily delete the line `self._echo_filter.record_tx(button, monotonic())` from the guard. Run the same command.
Expected: FAIL, `[1, 1, 1] != [1]`. Restore the line, run again, PASS.

**Step 4: Commit**

```bash
git add tests/test_cover_motion.py
git commit -m "test: a burst from the remote is repeated once"
```

---

### Task 4: A position command is never repeated

This is the defect the whole feature exists for: with a second node, Home Assistant's own UP comes back as an event.

**Files:**
- Test: `tests/test_cover_motion.py`

**Step 1: Write the test**

```python
async def test_home_assistants_own_command_is_never_repeated(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """A second node hears our UP; it must not be repeated, and the STOP holds.

    Issue #19: an automation repeating presses could not tell this echo from
    the remote, repeated it as a full open, and cancelled the STOP scheduled
    for the target.
    """
    entry = await _setup(hass, _make_entry(options=REPEAT))
    entry.runtime_data.cover._current_position = 0

    await hass.services.async_call(
        "cover",
        "set_cover_position",
        {"entity_id": ENTITY_ID, "position": 50},
        blocking=True,
    )
    # The other node reports our own UP, as a press would look.
    _fire_frame(hass, 1)
    await hass.async_block_till_done()
    assert [f["btn"] for f in frames] == [1]

    await asyncio.sleep(TRAVEL * 0.5 + 1.0)
    await hass.async_block_till_done()

    assert [f["btn"] for f in frames] == [1, 5]
    assert hass.states.get(ENTITY_ID).attributes["current_position"] == 50
```

**Step 2: Run it**

Run: `DOCKER_PYTEST tests/test_cover_motion.py -k own_command_is_never`
Expected: PASS, because the guard sits after the echo check.

**Step 3: Prove the test can fail**

Temporarily move the whole guard block above the `if self._echo_filter.is_echo(...)` check. Run again.
Expected: FAIL (an extra `1` in `frames`). Move it back, PASS.

**Step 4: Commit**

```bash
git add tests/test_cover_motion.py
git commit -m "test: Home Assistant's own command is never repeated"
```

---

### Task 5: What must never be repeated

**Files:**
- Test: `tests/test_cover_motion.py`

**Step 1: Write the three guards**

```python
async def test_nothing_is_repeated_with_the_option_off(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """The option is off by default: a press transmits nothing."""
    entry = await _setup(hass, _make_entry())
    entry.runtime_data.cover._current_position = 0

    _fire_frame(hass, 1)
    await hass.async_block_till_done()

    assert frames == []


async def test_the_led_button_is_never_repeated(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """LED toggles: repeating it would toggle it twice, so nothing changes."""
    await _setup(hass, _make_entry(options=REPEAT))

    _fire_frame(hass, 0, check=15)
    await hass.async_block_till_done()

    assert frames == []


async def test_a_mis_decoded_frame_is_never_repeated(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """A frame whose check contradicts its button is not put back on the air."""
    await _setup(hass, _make_entry(options=REPEAT))

    _fire_frame(hass, 1, check=15)
    await hass.async_block_till_done()

    assert frames == []
```

**Step 2: Run them**

Run: `DOCKER_PYTEST tests/test_cover_motion.py -k "option_off or led_button_is_never or mis_decoded_frame_is_never"`
Expected: 3 PASS.

**Step 3: Prove each can fail**, one mutation at a time, restoring after each:

- remove `self._repeat_remote and` from the guard: the option-off test fails;
- replace `button in (BUTTON_UP, BUTTON_DOWN, BUTTON_STOP)` with `True`: the LED test fails;
- move the guard above the `is_frame_consistent` check: the mis-decoded test fails.

**Step 4: Commit**

```bash
git add tests/test_cover_motion.py
git commit -m "test: what the repeater never sends"
```

---

### Task 6: A group press is repeated once, by the group cover

**Files:**
- Test: `tests/test_cover_motion.py` (after the group helpers)

**Step 1: Write the test**

```python
async def test_a_group_press_is_repeated_once_by_the_group_cover(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """Every sibling hears the common button; only its owner repeats it."""
    await _setup(hass, _make_group_entry(flagged=True, options=REPEAT))
    await _setup(hass, _make_entry(options=REPEAT))

    _fire_frame(hass, 1, channel=GROUP_CHANNEL)
    await hass.async_block_till_done()

    assert [(f["channel"], f["btn"]) for f in frames] == [(GROUP_CHANNEL, 1)]
```

**Step 2: Run it**

Run: `DOCKER_PYTEST tests/test_cover_motion.py -k group_press_is_repeated`
Expected: PASS.

**Step 3: Prove it can fail**

Remove `and event_channel == self._channel` from the guard. Run again.
Expected: FAIL, the sibling also sends `(5, 1)`. Restore, PASS.

**Step 4: Commit**

```bash
git add tests/test_cover_motion.py
git commit -m "test: a group press is repeated once, by its owner"
```

**Step 5: The siblings must recognise the repeated group frame (added after the Task 2 review)**

When the group cover repeats, only its own echo filter records the frame. A second node republishes the repeated group frame, and every sibling would take it as a fresh press: a sibling stopped in the meantime starts moving again in Home Assistant. `_async_drive_siblings` already arms the siblings for Home Assistant's own group commands; the repeat must do the same.

It must NOT be done in the guard: all covers handle the same original event synchronously and in no guaranteed order, so arming a sibling there could make it ignore the real press. Arm them in `_async_repeat`, which runs after every handler has seen the press.

Failing test first:

```python
async def test_the_siblings_ignore_the_echo_of_a_repeated_group_press(
    hass: HomeAssistant, frames: list[dict]
) -> None:
    """A second node hears our repeat of the common button: not a new press."""
    await _setup(hass, _make_group_entry(flagged=True, options=REPEAT))
    sibling = await _setup(hass, _make_entry())
    sibling.runtime_data.cover._current_position = 0

    _fire_frame(hass, 1, channel=GROUP_CHANNEL)
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == "opening"

    # The user stops that shutter; then the other node reports our repeat.
    await hass.services.async_call(
        "dooya", "mark_closed", {"entity_id": ENTITY_ID}, blocking=True
    )
    _fire_frame(hass, 1, channel=GROUP_CHANNEL)
    await hass.async_block_till_done()

    assert hass.states.get(ENTITY_ID).state != "opening"
```

Run: `DOCKER_PYTEST tests/test_cover_motion.py -k siblings_ignore_the_echo`
Expected: FAIL, the sibling is `opening` again.

Then in `_async_repeat`, before `_async_transmit`:

```python
        if self._is_broadcast:
            # Every sibling handles the common button too; the echo of this
            # repeat, heard by another node, must not look like a new press.
            now = monotonic()
            for cover in self._async_group_siblings():
                cover._echo_filter.record_tx(button, now)
```

Run it again: PASS. Full motion file green. Commit:

```bash
git add custom_components/dooya/cover.py tests/test_cover_motion.py
git commit -m "fix(cover): the siblings recognise a repeated group press"
```

---

### Task 7: A missing gateway does not break the press

**Files:**
- Modify: `custom_components/dooya/cover.py` (`_async_repeat`)
- Test: `tests/test_cover_motion.py`

**Step 1: Write the failing test**

No `frames` fixture here, so the ESPHome transmit service does not exist.

```python
async def test_a_repeat_without_a_gateway_does_not_break_the_press(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """The node is gone: the press still moves the estimate, and says why."""
    entry = await _setup(hass, _make_entry(options=REPEAT))
    entry.runtime_data.cover._current_position = 0

    _fire_frame(hass, 1)
    await hass.async_block_till_done()

    assert hass.states.get(ENTITY_ID).state == "opening"
    assert "could not repeat a press from the remote" in caplog.text
```

**Step 2: Run it to verify it fails**

Run: `DOCKER_PYTEST tests/test_cover_motion.py -k without_a_gateway`
Expected: FAIL on the missing log line: the `HomeAssistantError` escapes the task unhandled, so nothing explains it.

**Step 3: Catch it**

Replace the body of `_async_repeat` after the debug log with:

```python
        try:
            await self._async_transmit(button)
        except HomeAssistantError:
            # _async_transmit has already opened its repair issue. The press
            # itself reached Home Assistant and moved the estimate.
            _LOGGER.warning(
                "%s: could not repeat a press from the remote, its ESPHome "
                "node is not available",
                self._cover_name,
            )
```

**Step 4: Run it to verify it passes**

Run: `DOCKER_PYTEST tests/test_cover_motion.py -k without_a_gateway`
Expected: PASS.

**Step 5: Commit**

```bash
python -m ruff check . && python -m ruff format .
git add custom_components/dooya/cover.py tests/test_cover_motion.py
git commit -m "fix(cover): a repeat without a gateway does not break the press"
```

---

### Task 8: The option in the options flow

**Files:**
- Modify: `custom_components/dooya/config_flow.py` (const import; `current_is_awning` near line 505; the schema near line 560)
- Modify: `custom_components/dooya/strings.json`, `custom_components/dooya/translations/en.json`, `custom_components/dooya/translations/fr.json` (`options.step.init.data` and `.data_description`)
- Test: `tests/test_config_flow.py`

**Step 1: Write the failing test**

Add `CONF_REPEAT_REMOTE` to the const import of `tests/test_config_flow.py`, then after `test_options_can_mark_a_cover_as_the_common_button`:

```python
async def test_options_offer_to_repeat_the_remote_off_by_default(
    hass: HomeAssistant, gateway_service: list[dict]
) -> None:
    """The repeater is opt-in, per cover (issue #19)."""
    entry = await _add_cover(hass, channel=5, name="Salon")

    result = await hass.config_entries.options.async_init(entry.entry_id)
    field = next(
        key for key in result["data_schema"].schema if key == CONF_REPEAT_REMOTE
    )
    assert field.default() is False

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**OPTIONS_BASE, CONF_REPEAT_REMOTE: True}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_REPEAT_REMOTE] is True
```

**Step 2: Run it to verify it fails**

Run: `DOCKER_PYTEST tests/test_config_flow.py -k repeat_the_remote`
Expected: FAIL, `StopIteration`: the field is not in the schema.

**Step 3: Add the field**

In `config_flow.py`, add `CONF_REPEAT_REMOTE` to the const import. After `current_is_awning = ...`:

```python
        current_repeat_remote = bool(entry_value(entry, CONF_REPEAT_REMOTE, False))
```

In the schema dict, after the `CONF_IS_AWNING` line:

```python
                vol.Required(
                    CONF_REPEAT_REMOTE, default=current_repeat_remote
                ): bool,
```

**Step 4: Add the three translations**

In `strings.json` and, identically, `translations/en.json`, under `options.step.init`:

- `data.repeat_remote`: `"Repeat presses from the remote"`
- `data_description.repeat_remote`: `"Tick this only for a shutter the physical remote does not reach reliably. Each press on the remote for this shutter is sent again through this shutter's ESPHome node. Commands sent by Home Assistant are never repeated, so position commands keep working."`

In `translations/fr.json`:

- `data.repeat_remote`: `"Répéter les appuis de la télécommande"`
- `data_description.repeat_remote`: `"À cocher seulement pour un volet que la télécommande physique n'atteint pas bien. Chaque appui de la télécommande destiné à ce volet est renvoyé par le nœud ESPHome de ce volet. Les commandes envoyées par Home Assistant ne sont jamais répétées, donc les commandes de position continuent de fonctionner."`

**Step 5: Run the tests**

Run: `DOCKER_PYTEST tests/test_config_flow.py -k repeat_the_remote`
Expected: PASS.
Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_i18n_hygiene.py -q`
Expected: 4 passed (the three files carry the same keys, and no French outside `fr.json`).

**Step 6: Commit**

```bash
python -m ruff check . && python -m ruff format .
git add custom_components/dooya/config_flow.py custom_components/dooya/strings.json custom_components/dooya/translations/en.json custom_components/dooya/translations/fr.json tests/test_config_flow.py
git commit -m "feat(options): offer to repeat the remote, off by default"
```

---

### Task 9: Document it

**Files:**
- Modify: `README.md` (the "What you get" list, and a new section right after "RF Reliability (Repeat Count)")

**Step 1: A bullet in "What you get"**, after the LED bullet:

```markdown
- **A repeater for a weak remote.** Ticked on a shutter the remote does not
  reach, each press on the remote is sent again by the ESPHome node. Home
  Assistant's own commands are never repeated.
```

**Step 2: A section after "RF Reliability (Repeat Count)"**

```markdown
## A Remote That Does Not Reach Every Shutter

The ESPHome node often hears a remote that a distant shutter does not. Tick
**Repeat presses from the remote** in that shutter's options, and every press
on the remote meant for it is sent again, through the node configured for that
shutter.

It is off by default and set per shutter, so tick it only where it is needed.

What it never sends again:

- a command from Home Assistant itself. The integration knows the frames it
  just sent, so a position command is never repeated and its STOP holds. This
  is why it is an option here and not an automation: with two nodes, an
  automation cannot tell Home Assistant's frame from a press on the remote;
- the LED button, which toggles and would toggle twice;
- a frame that was decoded wrongly, or that belongs to no configured shutter.

A press is sent again once, however many copies the remote sends and however
many nodes hear it. A press on the remote's common button is repeated once, by
the cover that holds the group role.

If you built a repeater as an automation before, remove it when you tick this.
```

**Step 3: Commit**

```bash
python -c "t=open('README.md',encoding='utf-8').read(); print('em dashes:', t.count(chr(8212)))"
git add README.md
git commit -m "docs: the repeater for a weak remote"
```

The em dash count must not grow compared with `origin/main`.

---

### Task 10: Full suite, push, pull request

**Step 1: Everything green**

Run: `DOCKER_PYTEST`
Expected: 160 + 9 new = 169 passed, 28 skipped.
Run: `python -m ruff check . && python -m ruff format --check .`

**Step 2: Push and open the pull request**

```bash
git push -u origin feat/remote-repeater
gh pr create --repo dasimon135/ha-dooya --base main --head feat/remote-repeater --title "feat: repeat presses from a weak remote, as an option per cover" --body-file <body>
```

The body says why (issue #19, the broken position commands with two nodes), what is never repeated, the test list, and that live validation is still owed. It ends with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`. **Do not merge yet.**

---

### Task 11: Validate on the real Home Assistant

Same protocol as for #62 and #63: a phantom cover, id `FFFFFE`, channel 200, which no motor answers.

1. Announce the restart to the other sessions (ListAgents, SendMessage), wait two minutes, take the `ha-coord` lock by acting, never by deleting it.
2. Back up `H:\custom_components\dooya` to `H:\_backups\custom_components\` (never inside `custom_components`), deploy the branch's `custom_components/dooya`, restart Home Assistant.
3. Create the phantom cover (`ha_set_integration`, domain `dooya`, manual). Tick **Repeat presses from the remote** in its options.
4. Fire `esphome.dooya_received` `{id: "00FFFFFE", channel: 200, button: 1, check: 1}`: the log must show exactly one `transmit_dooya ... id=FFFFFE channel=200 button=1`.
5. Fire the same event three times in a row: one more transmission, not three.
6. `set_cover_position 50` on the phantom, then fire the event for its UP: no extra transmission, and the STOP line appears at the target.
7. Fire `{button: 0, check: 15}`: nothing transmitted.
8. Delete the phantom cover, tell the other sessions the validation is over.

Record the log lines in the pull request. Merge only then.

---

### After the plan

A pre-release `v0.13.0b1` (manifest bump pull request, release notes, `/release` skill) for the reporter of #19, who has two houses, two remotes and two nodes, and will remove his three automations. That release needs David's explicit go.
