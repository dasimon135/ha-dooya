# GitHub issue #14 — LED control (@Markus226)

> Target: <https://github.com/dasimon135/ha-dooya/issues/14>
> Opened, never answered. Language: English.
>
> Two things to get out of it: unblock him today (the ESPHome service is
> already generic, no integration change needed), and get the four facts
> needed before designing a real LED entity.
>
> The datapoint that matters: he recorded `button=0, check=15`. Every frame
> the integration sends today has `check == button` (UP 1/1, DOWN 3/3,
> STOP 5/5) and `check_for_button()` derives it that way on purpose. His
> capture is the first evidence that the check nibble is a per-command
> value, not a repeat of the button — which is exactly why this can't be a
> two-line patch.

---

Thanks, glad it's working for you — and thanks for capturing the frame, that's
the useful half of the request already done.

## You can do this today, no integration change needed

The ESPHome node isn't limited to up/down/stop. The `transmit_dooya` service in
[`esphome/dooya-node.yaml`](../esphome/dooya-node.yaml) takes whatever
button/check pair you hand it, so your LED frame is already sendable. Add this
to your `configuration.yaml` (or make it a script in the UI):

```yaml
script:
  toggle_blind_led:
    alias: "Toggle blind LED"
    sequence:
      - action: esphome.dooya_node_1_transmit_dooya
        data:
          dooya_id: 1411537   # 0x001589D1
          channel: 5
          btn: 0
          check: 15
```

Two things to adjust:

- `dooya_node_1` is the ESPHome node name from your own YAML — check
  **Developer tools → Actions** and type `esphome.` to find the real one.
- `dooya_id` is decimal. `0x001589D1` = `1411537`.

If you want a tile on the dashboard rather than a script, wrap it in a
[template button](https://www.home-assistant.io/integrations/button/) or just
add the script to a card — it shows up as a pressable row either way.

That should work right now. Let me know if it does, because it also confirms
the capture is complete.

## Why it isn't just a two-line patch

Your frame is `button=0, check=15`, and that's the interesting part.

Every frame the integration sends has `check == button`: up is `1/1`, down is
`3/3`, stop is `5/5`. That's not an accident — `check_for_button()` derives the
check nibble from the button precisely *because* a single stored value can't be
right for all three. Your LED command is the first evidence I have that the
check nibble is a per-command lookup rather than a copy of the button. So I
can't just add a fourth button code and reuse the existing path; there needs to
be a small command table, and I'd rather build that on more than one data point.

## What would help

If you can spare ten minutes with **Developer tools → Events → listen to
`esphome.dooya_received`**, four answers would let me design this properly:

1. **Is it a toggle?** Press the LED button 4–5 times in a row. Same frame
   (`button=0, check=15`) every time, LED alternating on/off? Or two different
   frames — one for on, one for off?
2. **Is the channel the LED's or the cover's?** Your capture says `channel=5`,
   same as your blind. If you have a second blind on another channel, does its
   LED button send that blind's channel?
3. **What hardware?** Motor/receiver reference, and the exact remote model
   (you said DC1600A — is that the one with a screen?).
4. **Any other buttons?** If your remote has P2, a favourite/preset key, or
   anything beyond up/down/stop, dumping those frames too would let me fill in
   the table in one pass instead of one issue per button.

## What I'd build

Assuming it's a toggle on the cover's own channel, the natural fit is an extra
**button entity** per blind ("Toggle LED"), off by default and enabled in the
options — a button rather than a switch or a light, because the protocol is
one-way and nothing tells us whether the LED actually came on. If it turns out
there are distinct on/off frames, then an assumed-state `light` becomes honest
and I'd do that instead.

Either way this is a good feature request — the LED is a real thing on a fair
number of these receivers and nobody has documented the frame publicly. Leaving
this open and tagging it as a feature.
