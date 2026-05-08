# Dooya RF Covers — Home Assistant Integration

Control Dooya RF433 motorized covers (blinds/shutters/rollers) from Home Assistant.

## Features

- **Open / Close / Stop** via RF433 OOK
- **Manual entry** — enter the hex ID directly (visible in ESPHome logs with `dump: dooya`)
- **Transmitter agnostic** — works with any HA `radio_frequency` transmitter:
  - ESPHome ESP32 + CC1101
  - Broadlink RM4 Pro
- **OEM brands supported**: Dooya, Cherub, Raex, Zemismart, and all clones using the same protocol

> 🚧 **Learning mode** (auto-detect ID from physical remote) — planned for a future release.

## Requirements

- Home Assistant 2026.5+
- A configured `radio_frequency` transmitter entity (433.92 MHz OOK)

## Installation (HACS)

1. Add this repository as a custom HACS integration
2. Install "Dooya RF Covers"
3. Restart Home Assistant
4. **Settings → Integrations → Add → Dooya RF Covers**

## Finding your Dooya ID

If using an ESPHome CC1101 receiver, you can retrieve your motor ID from the logs by adding `dump: dooya` to your `remote_receiver` configuration:

```yaml
remote_receiver:
  pin: GPIO4
  dump: dooya
```

Then press any button on your physical remote — the ID will appear in ESPHome logs.

## Protocol

Dooya RF433 OOK — timings (µs):

| Symbol | HIGH | LOW  |
|--------|------|------|
| Header | 5000 | 1500 |
| Bit 1  | 750  | 350  |
| Bit 0  | 350  | 750  |

Frame: `header + 24-bit ID + 8-bit channel + 4-bit button + 4-bit check`

Buttons: `UP=1`, `DOWN=3`, `STOP=5`

## License

MIT