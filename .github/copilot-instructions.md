# ha-dooya — Copilot Instructions

## Contexte

Intégration HACS pour les volets Dooya RF433 utilisant la plateforme `radio_frequency` de HA 2026.5+.

## Stack

- Python 3.12+
- HA custom component (`custom_components/dooya/`)
- Protocole RF433 OOK encodé en Python (`dooya_protocol.py`)
- Transmetteurs supportés : ESPHome CC1101, Broadlink RM4 Pro

## Conventions

- Langue : **français** (commentaires, commits, issues)
- Python : snake_case, annotations de type complètes
- 1 config entry = 1 volet
- Timings Dooya (µs) : Header 5000/1500 · Bit1 750/350 · Bit0 350/750
- Frame : header + 24b id + 8b channel + 4b button + 4b check (dernier bit = mark seul)
- Boutons : UP=1, DOWN=3, STOP=5 ; check = button par défaut

## Structure

```
custom_components/dooya/
├── __init__.py          # setup_entry / unload_entry
├── manifest.json        # domain, dependencies: [radio_frequency]
├── const.py             # constantes CONF_*, DOMAIN
├── config_flow.py       # user → learn → confirm / manual
├── entity.py            # DooyaBaseEntity (UUID transmetteur résistant renommage)
├── cover.py             # DooyaCover : open/close/stop → encode_dooya → async_send_command
├── dooya_protocol.py    # encode_dooya, decode_dooya, DooyaData
├── strings.json         # traductions EN (référence)
└── translations/
    ├── en.json
    └── fr.json
```

## Mode apprentissage

- ESPHome publie l'événement `esphome.dooya_received` quand une trame Dooya est reçue
- Le config flow écoute cet événement pendant 30 secondes (step `learn`)
- Format événement attendu : `{id: "00D1C917", channel: 5, button: 1, check: 1}`
