# Community forum — edits to apply to the original post

> **To actually post, use [`post-community-op-full.md`](post-community-op-full.md)**:
> it is the complete post with all of these edits already applied, ready to
> select-all / paste over the existing post. This file is the rationale — what
> changed and why — kept for the record.
>
> Regenerate the full version with `python tools/build_community_op.py`: it
> refetches `/raw/984671/1` and re-applies the eleven anchored edits, failing
> loudly if an anchor no longer matches (i.e. if the live post was edited
> in the meantime).
>
> Target: <https://community.home-assistant.io/t/control-dooya-rf433-blinds-with-esp32-cc1101-via-esphome/984671>
> post #1, last edited 2026-02-10 (version 2).
>
> This is a **patch**, not a rewrite. The post is ~20k characters and most of it
> is still accurate. Below are the blocks to change, in the order they appear.
>
> Reason for the edit:
> - a link to cpecorari's repo was promised in reply #9 and never added;
> - the ESPHome `cc1101` component went mainline (PR #11849, merged 2025-12-03,
>   shipped in ESPHome 2025.12), which makes the external `radiolib_cc1101`
>   component and two of the listed gotchas obsolete;
> - the tutorial ends on "position is unknown", which ha-dooya now solves.

---

## Edit 1 — add a banner right under the introduction

Insert immediately after the "Result: 8 blinds controlled from HA…" line.

```
---

**Update, 2026** — this write-up still works as published, but two things
changed since February and are worth reading before you start:

- ESPHome now ships a **built-in `cc1101` component** (since 2025.12), so the
  external `radiolib_cc1101` component below is no longer required. With it,
  TX and RX on separate pins in a single YAML work fine — see the *Updated
  wiring and config* section at the end.
- If you want a real cover entity with a position instead of three buttons,
  there is now an integration for that: see *Going further* at the end.

The original ESP-IDF + `radiolib_cc1101` config is left untouched below,
because it is what several people in this thread are running today.

---
```

---

## Edit 2 — rewrite the "Gotchas & tips" entries

Two of the five gotchas are only true for the `radiolib_cc1101` single-pin
setup. Replace those two entries; leave the frequency, `allow_other_uses` and
`repeat` entries in place but amend the frequency one.

### Replace: "RX + TX together = doesn't work"

```
⚠️ **RX + TX together — depends on your wiring**

With the single-pin `radiolib_cc1101` setup described above,
`remote_receiver` and `remote_transmitter` share GPIO4 and reception stops
working as soon as both are declared. Two separate YAML files (one for
sniffing, one for transmitting) is the workaround for that setup.

This is **not** a hardware limitation. If you wire GDO0 and GDO2 to two
different GPIOs, TX and RX coexist in a single YAML with no
`allow_other_uses` gymnastics at all. @cpecorari reported this in post #7
with GPIO12/GPIO27, and it is what I use myself now (GPIO4 for TX, GPIO16
for RX) with the mainline `cc1101` component.
```

### Replace: "Arduino framework = unstable TX"

```
⚠️ **Arduino framework — unstable TX in my setup, but not universally**

With `radiolib_cc1101` on the Arduino framework, my TX froze after a few
transmissions. Switching to ESP-IDF fixed it, and ESP-IDF is still what I
recommend. @cpecorari (post #7) runs Arduino with the mainline `cc1101`
component and reports no freezes, so this looks specific to the external
component rather than to Arduino itself.
```

### Amend: "Dooya frequency = 433.9205 MHz"

Append to the existing entry:

```
Note: this offset was needed with `radiolib_cc1101`. With the mainline
`cc1101` component I set a plain `433.92MHz` and everything responds. If
your blinds don't react, it is still the first setting to try nudging.
```

### Add a new gotcha at the end of the section

```
⚠️ **A silent non-transmitting build (reported, not reproduced by me)**

@cpecorari reports (post #7) that the ESPHome **CLI** on versions 2025.x and
2026.1.x – 2026.3.x compiles a binary that emits nothing at all: same YAML,
same chip, no RF, no error in the logs. Building through the ESPHome
dashboard add-on inside Home Assistant on ≥ 2026.4.5 works. The exact
regression was never isolated. I have not hit this myself, but if you are
convinced your config is right and nothing comes out of the antenna, try the
dashboard before you re-solder anything.

⚠️ **Some remotes send two frames per button**

Still from post #7: Naterial-branded remotes send two distinct RF frames for
each direction button (header + command, most likely). A single
`binary_sensor` matcher only catches one of the two, so you need two matchers
per direction button — and only one for STOP.
```

---

## Edit 3 — add two sections just before "Conclusion"

```
## Updated wiring and config (2026)

Since ESPHome 2025.12 there is a native `cc1101` component in ESPHome core
(<https://esphome.io/components/cc1101.html>). It replaces the external
`radiolib_cc1101` component, and because you no longer share one GPIO
between RX and TX, a single YAML does both jobs.

Wiring changes: keep SPI as described above (CS→GPIO5, SCK→GPIO18,
MOSI→GPIO23, MISO→GPIO19), wire **GDO0 → GPIO4** for transmission and
**GDO2 → GPIO16** for reception. Pin 8 of the module, listed as "not used"
in the wiring table above, is the one you now need.

A complete, commented node config using this — TX + RX, permanent listening,
one node per RF zone — is here:
<https://github.com/dasimon135/ha-dooya/blob/main/esphome/dooya-node.yaml>

RF range tip while you are at it: replace the module's coil antenna with a
straight 17.3 cm wire (a 433 MHz quarter wave) and keep the node high up and
away from reinforced concrete. It costs nothing and it is the single biggest
improvement I made to reliability.

## Going further

Two projects grew out of this thread and both are worth a look depending on
what you need.

**Raw capture and replay, with state sync from the physical remote** —
@cpecorari's build for a Naterial-branded (Dooya 433.88 MHz) awning. It
captures and replays raw frames instead of decoding the Dooya fields, and
updates the cover state in Home Assistant when someone presses the physical
remote. The `REVERSE_ENGINEERING.md` in the repo documents ten gotchas they
hit, several of which apply well beyond Naterial:
<https://github.com/cpecorari/esp32-naterial-awning>

**A cover entity with a position, instead of three buttons** — see the reply
further down this thread for `ha-dooya`, a custom integration that turns the
node above into one proper cover entity per blind.
```

---

## Edit 4 — amend the "position is unknown" note

The post currently ends the ESPHome-cover part with:

> Note: Without RF state feedback, the blind position is unknown. The cover
> will always show "unknown" state but commands work fine.

Append:

```
This is still true of a bare ESPHome cover: the Dooya protocol used here is
one-way, so the motor never tells you where it is. It can be worked around by
timing the travel rather than measuring it — @Haningback tried ESPHome's
`time_based` cover in post #5 and concluded the guessed position was more
annoying than three honest buttons, which matches my own experience. The
integration linked in *Going further* takes the same idea further: it measures
your real opening and closing times with a calibration assistant instead of
having you guess them, and it resyncs when it hears the physical remote.
```

---

## Edit 5 — refresh the "Tested with" footer

```
Tested with: ESPHome 2025.x–2026.x / ESP-IDF 5.x / ESP32 DevKit v1 /
CC1101 E07 green module / Home Assistant 2025.x+
Also reported working on ESP32-S3-WROOM1 N16R8 by @tzsolt (post #3).
```
