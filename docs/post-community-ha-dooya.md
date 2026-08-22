# Community forum — ha-dooya announcement

> Target: <https://community.home-assistant.io/t/control-dooya-rf433-blinds-with-esp32-cc1101-via-esphome/984671>
> Post as a new reply in the thread (not a reply to a specific person), after
> the original post has been edited to link to it from *Going further*.
>
> This is the English counterpart of `post-hacf.md` / `post-hacf-v080.md`.
> No announcement has ever been made on the English forum, so unlike the HACF
> follow-up this one introduces the integration from scratch.
>
> Two things to be careful about and both are in the text below:
> - the ESPHome YAML this needs is **not** the one in the tutorial (an API
>   service, not three template buttons) — say so plainly, people will
>   otherwise install it and wonder why nothing moves;
> - HACS default inclusion is still pending (hacs/default#9186), so the install
>   path is "custom repository".

---

Following up on my own tutorial, because the thread kept circling back to the
same limitation and I ended up doing something about it.

The write-up at the top gives you three buttons per blind and no idea where the
blind actually is. @Haningback tried ESPHome's `time_based` cover in post #5 and
concluded the guessed position was more annoying than three honest buttons —
which matched my experience exactly, and is why the original post says the state
will always show "unknown".

So I wrote a custom integration for it: **ha-dooya**.

<https://github.com/dasimon135/ha-dooya>

## What you get

One proper cover entity per blind, instead of three buttons:

- **Open / close / stop**, plus **set position** — partial opening from the
  Home Assistant UI, from scripts, from voice
- **Estimated position from your real travel times**. There's a calibration
  assistant that measures your opening and closing times with a stopwatch
  rather than asking you to guess them, which is the part that makes the
  difference against a hand-tuned `time_based` cover
- **Resync when the physical remote is used** — the node listens permanently,
  and a press on your DC90 updates the position in Home Assistant. Same
  echo-guard idea @cpecorari described in post #7
- **Recalibration** as buttons on the device page (mark as open, closed, or set
  a known position), for when the estimate has drifted
- **Favorite position** — per-blind, one button press, like the real remotes
- **Broadcast channel 0** — one entity that opens or closes every blind paired
  with the remote in a single RF frame
- **Automatic detection**: press UP on your physical remote and it reads the
  blind's ID for you. Manual entry too, if you already know it
- Entities go `unavailable` when the ESPHome node is offline, instead of
  silently pretending to work
- A **Lovelace card is bundled** (`custom:dooya-cover-card`) — animated shutter
  with position, presets and recalibration. Nothing extra to install
- Works with the OEM rebrands too: Dooya, Cherub, Raex, Zemismart and the other
  clones on the same protocol

Being clear about what it is *not*: the protocol is still one-way, so the
position remains an estimate, and the entity is `assumed_state`. Nothing here
reads the motor's real position, because the motor never tells anyone.

## What you need to change on the ESP32

**Your tutorial YAML will not work as-is** — this is the part to read before you
install anything.

The integration doesn't press your template buttons. It calls a native ESPHome
API service named `transmit_dooya`, and it listens for an
`esphome.dooya_received` event coming back from a `remote_receiver` with
`dump: dooya`. So you need:

- an ESPHome node exposing an `api:` service named `transmit_dooya`
- **"Allow the device to perform Home Assistant actions"** enabled in the
  ESPHome integration options — labelled *Allow service calls* on older Home
  Assistant versions. Without it the received events are dropped silently,
  which is a fun half hour
- ideally the mainline `cc1101` component with TX and RX on separate pins, so
  one node both transmits and listens

A complete commented node config is in the repo, and it's the one I run:
<https://github.com/dasimon135/ha-dooya/blob/main/esphome/dooya-node.yaml>

One node per RF zone if you have reinforced concrete walls — assign each blind
to its nearest node in the integration's options.

Requires Home Assistant 2026.5+.

## Installing

It's not in the HACS default store yet — the inclusion request is still pending
on their side. Until then:

1. HACS → three-dot menu → Custom repositories
2. Add `https://github.com/dasimon135/ha-dooya` as an **Integration**
3. Install "Dooya RF Covers", restart
4. Settings → Devices & Services → Add integration → Dooya RF Covers

Current version is v0.8.0, which came out of a deliberate bug hunt — four real
bugs found and fixed, and the test suite roughly doubled to cover the parts
that had none. There's a diagnostics
download on the device page; attaching it to an issue makes bugs enormously
easier to chase, and every bug worth fixing in this project so far was reported
by someone who had no idea what was wrong and just pasted the error.

Happy to answer questions here or in the repo's issues.
