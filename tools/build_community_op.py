import io, os, sys, urllib.request

sys.stdout.reconfigure(encoding="utf-8")

URL = "https://community.home-assistant.io/raw/984671/1"
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "docs", "post-community-op-full.md")

req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
src = urllib.request.urlopen(req).read().decode("utf-8")
src = src.replace("\r\n", "\n")
before = len(src)

edits = []


def sub(old, new, label):
    global src
    n = src.count(old)
    if n != 1:
        raise SystemExit(f"ANCHOR FAIL [{label}]: found {n} occurrences, expected 1")
    src = src.replace(old, new)
    edits.append(label)


# --- 1. banner under the introduction -------------------------------------
sub(
    "**Result**: 8 blinds controlled from HA, no cloud, no proprietary hub, for ~$10 worth of hardware.\n",
    """**Result**: 8 blinds controlled from HA, no cloud, no proprietary hub, for ~$10 worth of hardware.

> **Update, 2026** — this write-up still works exactly as published, but two things have changed since February and are worth knowing before you start.
>
> - ESPHome now ships a **built-in `cc1101` component** (since 2025.12), so the external `radiolib_cc1101` component used below is no longer required. With it, TX and RX on **separate pins** in a **single YAML** work fine — see *Updated wiring and config (2026)* near the end.
> - If you want a real cover entity with a position instead of three buttons, there is now an integration for that — see *Going further* at the end.
>
> The original ESP-IDF + `radiolib_cc1101` config is left untouched below, because it is what several people in this thread are running today.
""",
    "banner",
)

# --- 2. key points nuance --------------------------------------------------
sub(
    "- **ESP-IDF framework required**: the Arduino framework does not work correctly for TX with the CC1101",
    "- **ESP-IDF framework required** with `radiolib_cc1101`: the Arduino framework does not work correctly for TX in this setup (see the gotchas at the end for the nuance)",
    "key-points",
)

# --- 3. "position is unknown" note ----------------------------------------
sub(
    '> Note: Without RF state feedback, the blind position is unknown. The cover will always show "unknown" state but commands work fine.',
    '> Note: Without RF state feedback, the blind position is unknown. The cover will always show "unknown" state but commands work fine.\n\nThis is still true of a bare ESPHome cover: the Dooya protocol used here is one-way, so the motor never tells you where it is. It can be worked around by *timing* the travel rather than measuring it — @Haningback tried ESPHome\'s `time_based` cover in post #5 and concluded the guessed position was more annoying than three honest buttons, which matches my own experience. The integration linked in *Going further* takes the same idea further: it measures your real opening and closing times with a calibration assistant instead of having you guess them, and it resyncs when it hears the physical remote.',
    "position-note",
)

# --- 4. gotcha: RX + TX ----------------------------------------------------
sub(
    "### ❌ RX + TX together = doesn't work\n"
    "`remote_receiver` and `remote_transmitter` share the same GPIO4. When both are in the same config, **reception stops working**, even when not transmitting. Solution: two separate YAML files — one for sniffing, one for transmitting.",
    "### ⚠️ RX + TX together — depends on your wiring\n"
    "With the single-pin `radiolib_cc1101` setup described above, `remote_receiver` and `remote_transmitter` share GPIO4, and **reception stops working** as soon as both are declared, even when not transmitting. Two separate YAML files — one for sniffing, one for transmitting — is the workaround for that setup.\n\n"
    "This is **not** a hardware limitation. Wire GDO0 and GDO2 to two different GPIOs and TX and RX coexist in a single YAML, with no `allow_other_uses` gymnastics at all. @cpecorari reported this in post #7 with GPIO12/GPIO27, and it is what I run myself now (GPIO4 for TX, GPIO16 for RX) with the mainline `cc1101` component.",
    "gotcha-rxtx",
)

# --- 5. gotcha: Arduino ----------------------------------------------------
sub(
    "### ❌ Arduino framework = unstable TX\n"
    "With the Arduino framework, TX freezes after a few transmissions. **Switch to ESP-IDF**, it's the only stable config.",
    "### ⚠️ Arduino framework = unstable TX (with `radiolib_cc1101`)\n"
    "With `radiolib_cc1101` on the Arduino framework, my TX froze after a few transmissions. **Switching to ESP-IDF** fixed it, and ESP-IDF is still what I recommend. @cpecorari (post #7) runs Arduino with the mainline `cc1101` component and reports no freezes, so this looks specific to the external component rather than to Arduino itself.",
    "gotcha-arduino",
)

# --- 6. gotcha: frequency --------------------------------------------------
sub(
    "This is NOT standard 433.92 MHz. The exact frequency is **433.9205 MHz**. If your blinds don't respond, check this setting.",
    "This is NOT standard 433.92 MHz. The exact frequency is **433.9205 MHz**. If your blinds don't respond, check this setting.\n\n"
    "Note: this offset was needed with `radiolib_cc1101`. With the mainline `cc1101` component I set a plain `433.92MHz` and everything responds. Either way, if your blinds don't react this is still the first setting to nudge.",
    "gotcha-freq",
)

# --- 7. gotcha: allow_other_uses ------------------------------------------
sub(
    "### ✅ `allow_other_uses: true` is mandatory\n"
    "GPIO4 is used by both `radiolib_cc1101` (rx_pin) and `remote_transmitter` (pin). You must add `allow_other_uses: true` on both declarations, otherwise ESPHome refuses to compile.",
    "### ✅ `allow_other_uses: true` is mandatory (single-pin setup)\n"
    "GPIO4 is used by both `radiolib_cc1101` (rx_pin) and `remote_transmitter` (pin). You must add `allow_other_uses: true` on both declarations, otherwise ESPHome refuses to compile. This disappears entirely if you put RX and TX on separate pins.",
    "gotcha-allow",
)

# --- 8. two new gotchas at the end of the section --------------------------
sub(
    "### ✅ The `repeat` matters\n"
    "Dooya motors need to receive the code multiple times to react. `repeat: { times: 5 }` is a good balance between reliability and speed.",
    "### ✅ The `repeat` matters\n"
    "Dooya motors need to receive the code multiple times to react. `repeat: { times: 5 }` is a good balance between reliability and speed.\n\n"
    "### ⚠️ A silent non-transmitting build (reported, not reproduced by me)\n"
    "@cpecorari reports in post #7 that the ESPHome **CLI** on versions 2025.x and 2026.1.x – 2026.3.x compiles a binary that emits nothing at all: same YAML, same chip, no RF, no error in the logs. Building through the **ESPHome dashboard add-on** inside Home Assistant on ≥ 2026.4.5 works. The exact regression was never isolated. I have not hit this myself, but if you are convinced your config is right and nothing comes out of the antenna, try the dashboard before you re-solder anything.\n\n"
    "### ⚠️ Some remotes send two frames per button\n"
    "Still from post #7: Naterial-branded remotes send two distinct RF frames for each direction button (header + command, most likely). A single `binary_sensor` matcher only catches one of the two, so you need **two matchers per direction button** — and only one for STOP.",
    "gotcha-new",
)

# --- 9. external component section ----------------------------------------
sub(
    "- The Dooya protocol is natively supported by ESPHome (`remote_transmitter.transmit_dooya`)",
    "- The Dooya protocol is natively supported by ESPHome (`remote_transmitter.transmit_dooya`)\n\n"
    "**Since ESPHome 2025.12 this external component is optional**: a [`cc1101` component](https://esphome.io/components/cc1101.html) is now part of ESPHome core. See the updated config below.",
    "external-component",
)

# --- 10. new sections before the conclusion --------------------------------
sub(
    "## Conclusion\n",
    """## Updated wiring and config (2026)

Since ESPHome 2025.12 there is a native [`cc1101` component](https://esphome.io/components/cc1101.html) in ESPHome core. It replaces the external `radiolib_cc1101` component, and because you no longer share one GPIO between RX and TX, **a single YAML does both jobs**.

Wiring changes: keep SPI as described above (CS → GPIO5, SCK → GPIO18, MOSI → GPIO23, MISO → GPIO19), then wire **GDO0 → GPIO4** for transmission and **GDO2 → GPIO16** for reception. Pin 8 of the module, listed as "not used" in the wiring table near the top, is the one you now need.

A complete, commented node config using this — TX + RX, permanent listening, one node per RF zone — is here:
https://github.com/dasimon135/ha-dooya/blob/main/esphome/dooya-node.yaml

RF range tip while you are at it: replace the module's coil antenna with a straight **17.3 cm** wire (a 433 MHz quarter wave), and keep the node high up and away from reinforced concrete. It costs nothing and it was the single biggest reliability improvement I made.

---

## Going further

Two projects grew out of this thread, and which one you want depends on what you need.

**Raw capture and replay, with state sync from the physical remote** — @cpecorari's build for a Naterial-branded (Dooya 433.88 MHz) awning. It captures and replays raw frames instead of decoding the Dooya fields, and updates the cover state in Home Assistant when someone presses the physical remote. The `REVERSE_ENGINEERING.md` in the repo documents ten gotchas they hit, several of which apply well beyond Naterial:
https://github.com/cpecorari/esp32-naterial-awning

**A cover entity with a position, instead of three buttons** — see the reply further down this thread for `ha-dooya`, a custom integration that turns the node above into one proper cover entity per blind, with a position estimated from your measured travel times.

---

## Conclusion
""",
    "new-sections",
)

# --- 11. footer ------------------------------------------------------------
sub(
    "*Tested with: ESPHome 2025.x / ESP-IDF 5.x / ESP32 DevKit v1 / CC1101 E07 green module / Home Assistant 2025.x+*",
    "*Tested with: ESPHome 2025.x–2026.x / ESP-IDF 5.x / ESP32 DevKit v1 / CC1101 E07 green module / Home Assistant 2025.x+*\n"
    "*Also reported working on ESP32-S3-WROOM1 N16R8 by @tzsolt (post #3).*",
    "footer",
)

with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
    f.write(src)

print("edits applied:", ", ".join(edits))
print(f"chars {before} -> {len(src)}  (+{len(src) - before})")
print("written:", OUT)
