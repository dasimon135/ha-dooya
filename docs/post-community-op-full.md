# [Tutorial] Control Dooya RF433 Blinds with ESP32 + CC1101 via ESPHome

## Introduction

Hey everyone!

Sharing my setup for controlling **Dooya roller blinds** (RF433 MHz motors) from **Home Assistant** using an **ESP32** and a **CC1101** module running **ESPHome**.

Dooya blinds (and rebrands like Zemismart, AM43, etc.) use RF 433 MHz remotes with a proprietary protocol. The idea: replace all DC90 remotes with a single ESP32 that transmits the same RF codes.

**Result**: 8 blinds controlled from HA, no cloud, no proprietary hub, for ~$10 worth of hardware.

> **Update, 2026** — this write-up still works exactly as published, but two things have changed since February and are worth knowing before you start.
>
> - ESPHome now ships a **built-in `cc1101` component** (since 2025.12), so the external `radiolib_cc1101` component used below is no longer required. With it, TX and RX on **separate pins** in a **single YAML** work fine — see *Updated wiring and config (2026)* near the end.
> - If you want a real cover entity with a position instead of three buttons, there is now an integration for that — see *Going further* at the end.
>
> The original ESP-IDF + `radiolib_cc1101` config is left untouched below, because it is what several people in this thread are running today.

---

## Hardware

| Component | Approx. Price | Source |
|-----------|---------------|--------|
| ESP32 DevKit V1 (or clone) | ~$4 | AliExpress |
| CC1101 433MHz module (green E07, 8 pins) | ~$3 | AliExpress |
| Dupont jumper wires (female-female) | ~$2 | AliExpress |
| Micro-USB cable + 5V charger | already have | - |

**Total: ~$10**

### Optional for final installation
- Plastic enclosure (~83x58x33mm)
- PG7 cable gland (USB cable passthrough)
- 3M 9448A double-sided tape (mounting inside enclosure)

---

## Wiring: ESP32 + CC1101

### Identify your CC1101 module

There are two common versions of the 8-pin CC1101 module. Check **pin 2**:

- **GREEN module (E07)**: Pin 2 = **VCC** (3.3V)
- **BLUE module (Standard)**: Pin 2 = **GND**

### Wiring for GREEN module (E07) — most common on AliExpress

| CC1101 Pin | Name | ESP32 GPIO | Function |
|:---:|:---|:---|:---|
| 1 | GND | GND | Ground |
| 2 | VCC | 3V3 | 3.3V Power |
| 3 | GDO0 | GPIO 4 | RX/TX (RF data) |
| 4 | CSN | GPIO 5 | SPI Chip Select |
| 5 | SCK | GPIO 18 | SPI Clock |
| 6 | MOSI | GPIO 23 | SPI MOSI |
| 7 | MISO | GPIO 19 | SPI MISO |
| 8 | GDO2 | *(not used)* | - |

### Wiring for BLUE module (Standard)

| CC1101 Pin | Name | ESP32 GPIO | Function |
|:---:|:---|:---|:---|
| 1 | VCC | 3V3 | 3.3V Power |
| 2 | GND | GND | Ground |
| 3 | MOSI | GPIO 23 | SPI MOSI |
| 4 | SCLK | GPIO 18 | SPI Clock |
| 5 | MISO | GPIO 19 | SPI MISO |
| 6 | GDO2 | *(not used)* | - |
| 7 | GDO0 | GPIO 4 | RX/TX |
| 8 | CSN | GPIO 5 | SPI Chip Select |

> ⚠️ **Warning**: The CC1101 runs on **3.3V only**. Do NOT connect it to 5V or you'll fry it.

---

## Step 1: Sniff your remote codes

Before you can transmit, you need to capture the RF codes from each Dooya remote. Each remote has a **unique ID** (24-bit) that is paired to the blind motor.

### ESPHome RX config (sniffer)

> ⚠️ **Critical**: Reception only works when `remote_receiver` is used **alone**, without `remote_transmitter` in the same config. This is a limitation of sharing GPIO4 between RX and TX.

```yaml
substitutions:
  device_name: esp32-rf433-sniffer
  friendly_name: "RF433 Sniffer"

esphome:
  name: ${device_name}
  friendly_name: ${friendly_name}
  on_boot:
    priority: -100
    then:
      - lambda: id(mycc1101).recv();

esp32:
  board: esp32dev
  framework:
    type: esp-idf

external_components:
  - source: github://juanboro/esphome-radiolib-cc1101@main
    components: [ radiolib_cc1101 ]

wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password
  power_save_mode: none
  fast_connect: true
  ap:
    ssid: "${device_name}-fallback"
    password: "12345678"

captive_portal:

logger:
  level: DEBUG

api:

ota:
  - platform: esphome
    password: "1234"

web_server:
  port: 80

spi:
  id: spi_bus
  type: single
  clk_pin: GPIO18
  mosi_pin: GPIO23
  miso_pin: GPIO19

radiolib_cc1101:
  id: mycc1101
  cs_pin: 5
  rx_pin:
    number: 4
    allow_other_uses: true
  frequency: 433.9205
  filter: 468khz
  bitrate: 5

# Receiver ONLY - NO remote_transmitter!
remote_receiver:
  id: rf_receiver
  pin:
    number: 4
    allow_other_uses: true
  dump: all
```

### How to sniff

1. Flash this config to the ESP32
2. Open the **ESPHome logs** (via dashboard or `esphome logs`)
3. Press a button on your DC90 remote (Up, Stop, or Down)
4. Look for a log line like:
```
Received Dooya: id=0x00D1C917, channel=5, button=1, check=1
```
5. Write down `id`, `channel`, `button`, and `check` for each button
6. Repeat for each remote

### Dooya protocol

- **id**: 24-bit, unique per remote (paired to the motor)
- **channel**: usually 5 for single-channel remotes
- **button**: 1 = Up, 3 = Down, 5 = Stop
- **check**: usually equals button value

---

## Step 2: Configure TX (transmitter)

Once you've captured all codes, switch to the TX config. Remove `remote_receiver` and add `remote_transmitter` instead.

### ESPHome TX config

```yaml
substitutions:
  device_name: esp32-blinds-rf433
  friendly_name: "Dooya Blinds RF433"

esphome:
  name: ${device_name}
  friendly_name: ${friendly_name}

esp32:
  board: esp32dev
  framework:
    type: esp-idf

external_components:
  - source: github://juanboro/esphome-radiolib-cc1101@main
    components: [ radiolib_cc1101 ]

wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password
  power_save_mode: none
  fast_connect: true
  ap:
    ssid: "${device_name}-fallback"
    password: "12345678"

captive_portal:

logger:
  level: DEBUG

api:

ota:
  - platform: esphome
    password: "1234"

web_server:
  port: 80

# SPI config for CC1101
spi:
  id: spi_bus
  type: single
  clk_pin: GPIO18
  mosi_pin: GPIO23
  miso_pin: GPIO19

# RadioLib CC1101 - Dooya settings
radiolib_cc1101:
  id: mycc1101
  cs_pin: 5
  rx_pin:
    number: 4
    allow_other_uses: true
  frequency: 433.9205
  filter: 468khz
  bitrate: 5

# RF transmitter on GDO0 (GPIO4)
remote_transmitter:
  - id: rf_transmitter
    pin:
      number: 4
      allow_other_uses: true
    carrier_duty_percent: 100%
    non_blocking: false
    on_transmit:
      then:
        - lambda: id(mycc1101).xmit();
    on_complete:
      then:
        - lambda: id(mycc1101).recv();

# === Buttons per blind ===
# Duplicate this block for each blind, changing the name and ID
button:
  # --- Living Room Blind ---
  - platform: template
    name: "Living Room Blind - Up"
    id: blind_living_up
    icon: "mdi:arrow-up-bold-box"
    on_press:
      - remote_transmitter.transmit_dooya:
          transmitter_id: rf_transmitter
          id: 0x00D1C917        # <-- Replace with YOUR remote's ID
          channel: 5
          button: 1
          check: 1
          repeat: { times: 5, wait_time: 1ms }

  - platform: template
    name: "Living Room Blind - Stop"
    id: blind_living_stop
    icon: "mdi:stop-circle"
    on_press:
      - remote_transmitter.transmit_dooya:
          transmitter_id: rf_transmitter
          id: 0x00D1C917
          channel: 5
          button: 5
          check: 5
          repeat: { times: 5, wait_time: 1ms }

  - platform: template
    name: "Living Room Blind - Down"
    id: blind_living_down
    icon: "mdi:arrow-down-bold-box"
    on_press:
      - remote_transmitter.transmit_dooya:
          transmitter_id: rf_transmitter
          id: 0x00D1C917
          channel: 5
          button: 3
          check: 3
          repeat: { times: 5, wait_time: 1ms }
```

### Key points

- `repeat: { times: 5, wait_time: 1ms }` sends the code 5 times for reliable motor reception
- The `on_transmit` / `on_complete` lambdas switch the CC1101 between TX mode and idle — this is mandatory
- **ESP-IDF framework required** with `radiolib_cc1101`: the Arduino framework does not work correctly for TX in this setup (see the gotchas at the end for the nuance)

---

## Step 3: Home Assistant integration

Buttons automatically appear in HA via the ESPHome integration. You'll get 3 buttons per blind: Up, Stop, Down.

### Create a Cover entity (optional)

For a proper blind entity in HA with up/down/stop controls, create a `template cover` in your `configuration.yaml`:

```yaml
cover:
  - platform: template
    covers:
      blind_living_room:
        device_class: shutter
        friendly_name: "Living Room Blind"
        open_cover:
          - action: button.press
            target:
              entity_id: button.living_room_blind_up
        close_cover:
          - action: button.press
            target:
              entity_id: button.living_room_blind_down
        stop_cover:
          - action: button.press
            target:
              entity_id: button.living_room_blind_stop
```

> Note: Without RF state feedback, the blind position is unknown. The cover will always show "unknown" state but commands work fine.

This is still true of a bare ESPHome cover: the Dooya protocol used here is one-way, so the motor never tells you where it is. It can be worked around by *timing* the travel rather than measuring it — @Haningback tried ESPHome's `time_based` cover in post #5 and concluded the guessed position was more annoying than three honest buttons, which matches my own experience. The integration linked in *Going further* takes the same idea further: it measures your real opening and closing times with a calibration assistant instead of having you guess them, and it resyncs when it hears the physical remote.

---

## Enclosure (final installation)

Once everything works on the breadboard:

1. **Solder** wires directly onto the ESP32 pins (component side)
2. **Cut** the protruding pins on the back with flush cutters (or bend them flat if you want to keep the breadboard option)
3. **Mount** the ESP32 and CC1101 inside the enclosure with 3M 9448A double-sided tape
4. **Drill** a hole for the USB cable (PG7 cable gland = clean and solid)
5. The CC1101 antenna can stay inside if the enclosure is **plastic** (RF signal passes through)

### Placement

Place the enclosure **centrally** relative to your blinds for optimal range. The CC1101 has a range of ~30-50m indoors, more than enough for a house.

---

## Gotchas & tips

### ⚠️ RX + TX together — depends on your wiring
With the single-pin `radiolib_cc1101` setup described above, `remote_receiver` and `remote_transmitter` share GPIO4, and **reception stops working** as soon as both are declared, even when not transmitting. Two separate YAML files — one for sniffing, one for transmitting — is the workaround for that setup.

This is **not** a hardware limitation. Wire GDO0 and GDO2 to two different GPIOs and TX and RX coexist in a single YAML, with no `allow_other_uses` gymnastics at all. @cpecorari reported this in post #7 with GPIO12/GPIO27, and it is what I run myself now (GPIO4 for TX, GPIO16 for RX) with the mainline `cc1101` component.

### ⚠️ Arduino framework = unstable TX (with `radiolib_cc1101`)
With `radiolib_cc1101` on the Arduino framework, my TX froze after a few transmissions. **Switching to ESP-IDF** fixed it, and ESP-IDF is still what I recommend. @cpecorari (post #7) runs Arduino with the mainline `cc1101` component and reports no freezes, so this looks specific to the external component rather than to Arduino itself.

### ✅ Dooya frequency = 433.9205 MHz
This is NOT standard 433.92 MHz. The exact frequency is **433.9205 MHz**. If your blinds don't respond, check this setting.

Note: this offset was needed with `radiolib_cc1101`. With the mainline `cc1101` component I set a plain `433.92MHz` and everything responds. Either way, if your blinds don't react this is still the first setting to nudge.

### ✅ `allow_other_uses: true` is mandatory (single-pin setup)
GPIO4 is used by both `radiolib_cc1101` (rx_pin) and `remote_transmitter` (pin). You must add `allow_other_uses: true` on both declarations, otherwise ESPHome refuses to compile. This disappears entirely if you put RX and TX on separate pins.

### ✅ The `repeat` matters
Dooya motors need to receive the code multiple times to react. `repeat: { times: 5 }` is a good balance between reliability and speed.

### ⚠️ A silent non-transmitting build (reported, not reproduced by me)
@cpecorari reports in post #7 that the ESPHome **CLI** on versions 2025.x and 2026.1.x – 2026.3.x compiles a binary that emits nothing at all: same YAML, same chip, no RF, no error in the logs. Building through the **ESPHome dashboard add-on** inside Home Assistant on ≥ 2026.4.5 works. The exact regression was never isolated. I have not hit this myself, but if you are convinced your config is right and nothing comes out of the antenna, try the dashboard before you re-solder anything.

### ⚠️ Some remotes send two frames per button
Still from post #7: Naterial-branded remotes send two distinct RF frames for each direction button (header + command, most likely). A single `binary_sensor` matcher only catches one of the two, so you need **two matchers per direction button** — and only one for STOP.

---

## External component used

- **[esphome-radiolib-cc1101](https://github.com/juanboro/esphome-radiolib-cc1101)** by juanboro
- Based on the RadioLib library, enables CC1101 usage in OOK direct mode with ESPHome
- The Dooya protocol is natively supported by ESPHome (`remote_transmitter.transmit_dooya`)

**Since ESPHome 2025.12 this external component is optional**: a [`cc1101` component](https://esphome.io/components/cc1101.html) is now part of ESPHome core. See the updated config below.

---

## Updated wiring and config (2026)

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

This works flawlessly for my setup of 8 Dooya blinds. The CC1101 is far more reliable than a basic 433 MHz transmitter because it allows precise frequency tuning (433.9205 MHz vs generic 433.92).

Total cost is ridiculously low (~$10) compared to proprietary Zigbee/WiFi solutions, and everything stays 100% local via Home Assistant.

Feel free to ask if you have any questions! 🙂

---

*Tested with: ESPHome 2025.x–2026.x / ESP-IDF 5.x / ESP32 DevKit v1 / CC1101 E07 green module / Home Assistant 2025.x+*
*Also reported working on ESP32-S3-WROOM1 N16R8 by @tzsolt (post #3).*