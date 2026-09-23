# Repeating presses from a weak remote

Design validated on 2026-09-23. Origin: issue #19.

## Why

A Dooya remote with a weak signal reaches some shutters and not others. The
ESPHome node hears the remote fine; the fix users reach for is to have the node
send the frame again.

Done as a user automation, that breaks as soon as a second node is in range.
Home Assistant sends UP for a `set_position`; the second node hears that frame
and republishes it; the automation cannot tell it apart from a press on the
remote and repeats it, or worse, calls `cover.open_cover`, which cancels the
STOP scheduled for the target. Reported on #19 on 2026-09-23 by a user with two
houses, 15 and 19 shutters, two remotes and two nodes.

The integration can make the distinction an automation cannot: it remembers every
frame it sent for two seconds (`TxEchoFilter`), it already drops mis-decoded
frames (`is_frame_consistent`), and it knows which cover owns each id and channel.

This was declined twice as belonging in a generic RF gateway. It is reversed
because no user-side construction can be made correct.

## Behaviour

An option per cover, **off by default**: repeat presses from the remote. Only
worth ticking on a shutter the remote does not reach.

When it is on, a frame heard for that cover is sent again, through that cover's
configured node, if and only if:

- it is UP, DOWN or STOP. Never the LED button: it toggles, so repeating it
  would toggle twice;
- it is not an echo of a frame Home Assistant sent in the last two seconds, so
  position commands are never repeated;
- it is consistent (check nibble matches the button), so a mis-decoded frame is
  never put back on the air;
- its channel is exactly this cover's channel. An id and channel belong to one
  entry, so each press is repeated once. A group press is repeated only by the
  cover holding the group role, not by each sibling.

One repeat per press: the first copy of the remote's burst claims it, and the
following copies, like the echo of the repeat heard by another node, fall inside
the echo window and are ignored.

The estimated position is not touched: the press has already started the
estimated movement, and the repeat only transmits.

The repeat is sent immediately, as the user's automation did; that user reports
it working in both houses.

## Architecture

- `const.py`: `CONF_REPEAT_REMOTE = "repeat_remote"`.
- `config_flow.py`: a checkbox in the options flow only, default `False`, next
  to the group and awning checkboxes. Not in the creation flow: it is set once a
  shutter turns out to be out of reach.
- `strings.json`, `translations/en.json`, `translations/fr.json`: label and help
  text (only for a shutter the remote cannot reach; Home Assistant's own commands
  are never repeated; this cover's node transmits).
- `cover.py`, in `_handle_dooya_event`, after the echo check and before the
  estimate update:

  ```python
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

  `record_tx` runs synchronously so the next copy of the burst, a few
  milliseconds later, is already an echo. `_async_repeat` calls the existing
  `_async_transmit(button)`: this cover's node, `repeat_count`, echo recording.
  The physical button is repeated as heard, so an awning needs no mapping.

No change to the ESPHome configuration, no new service, no new entity.

## Edge cases

- Gateway missing or offline: `_async_transmit` raises and opens its repair
  issue; `_async_repeat` catches it and logs a warning. The estimate has already
  started.
- A genuine press within two seconds of Home Assistant sending the same button
  is taken for an echo and not repeated. The estimate already treats it so.
- Entry reloaded during a repeat: the task belongs to the entry, the unload waits.
- Option off: first condition, nothing changes.

## Tests

Each must fail on the current code first.

1. Option off: a press transmits nothing.
2. Option on: a press transmits exactly one frame, with this cover's id and
   channel.
3. A burst of three copies gives one repeat.
4. `set_cover_position` with the option on, then the echo of its UP: no repeat,
   and the STOP still goes out at the target.
5. An LED frame is never repeated.
6. A mis-decoded frame is never repeated.
7. A group press is repeated once, by the group cover.
8. A missing gateway does not break the press.
9. The options flow offers the checkbox, off by default.

## Validation and release

On the maintainer's Home Assistant, on a test cover whose id no motor answers:
a replayed remote press gives one transmission; a position command followed by
its echo gives none, and the STOP is on time.

Not verifiable here: the range gained with two nodes and a weak remote. Shipped
as a pre-release (v0.13.0b1) for the reporter of #19 to validate in both houses,
removing his three automations, then promoted.
