"""Encodage du protocole Dooya RF433 (OOK).

Timings extraits de ESPHome dooya_protocol.cpp :
- Header  : 5000 µs HIGH + 1500 µs LOW
- Bit 0   : 350 µs HIGH + 750 µs LOW
- Bit 1   : 750 µs HIGH + 350 µs LOW
- Trame   : header + 24 bits id + 8 bits channel + 4 bits button + 4 bits check

Référence : https://github.com/esphome/esphome/blob/dev/esphome/components/remote_base/dooya_protocol.cpp
"""

from __future__ import annotations

from dataclasses import dataclass

# Timings en µs (µsecondes)
HEADER_HIGH_US: int = 5000
HEADER_LOW_US: int = 1500
BIT_ZERO_HIGH_US: int = 350
BIT_ZERO_LOW_US: int = 750
BIT_ONE_HIGH_US: int = 750
BIT_ONE_LOW_US: int = 350

# Fréquence Dooya RF433 en Hz
DOOYA_FREQUENCY_HZ: int = 433_920_000

# Boutons Dooya
BUTTON_UP: int = 1
BUTTON_DOWN: int = 3
BUTTON_STOP: int = 5


@dataclass
class DooyaData:
    """Données d'une commande Dooya.

    Attributs:
        id      : identifiant de la télécommande (24 bits)
        channel : canal du volet (8 bits, 1-16 typiquement)
        button  : code bouton — 1=monter, 3=descendre, 5=stop (4 bits)
        check   : checksum/code de contrôle (4 bits, souvent == button)
    """

    id: int
    channel: int
    button: int
    check: int


def encode_dooya(data: DooyaData) -> list[int]:
    """Encode une commande Dooya en liste de timings OOK (µs).

    Format de la liste retournée : [high, low, high, low, ...]
    Compatible avec ESPHome remote_transmitter et avec une éventuelle
    réutilisation côté Home Assistant.

    Args:
        data: données de la commande Dooya

    Returns:
        Liste de timings en µs alternant HIGH/LOW, commençant par HIGH.
    """
    timings: list[int] = []

    def _add_item(high: int, low: int) -> None:
        timings.append(high)
        timings.append(low)

    def _encode_bits(value: int, nbits: int) -> None:
        for shift in range(nbits - 1, -1, -1):
            if (value >> shift) & 1:
                _add_item(BIT_ONE_HIGH_US, BIT_ONE_LOW_US)
            else:
                _add_item(BIT_ZERO_HIGH_US, BIT_ZERO_LOW_US)

    # Header
    _add_item(HEADER_HIGH_US, HEADER_LOW_US)

    # id : 24 bits
    _encode_bits(data.id, 24)

    # channel : 8 bits
    _encode_bits(data.channel, 8)

    # button : 4 bits
    _encode_bits(data.button, 4)

    # check : 4 bits (dernier bit = mark uniquement, pas de LOW final)
    # Les 3 premiers bits sont des items complets (high+low)
    for shift in range(3, 0, -1):
        if (data.check >> shift) & 1:
            _add_item(BIT_ONE_HIGH_US, BIT_ONE_LOW_US)
        else:
            _add_item(BIT_ZERO_HIGH_US, BIT_ZERO_LOW_US)
    # Dernier bit du check : mark uniquement (conforme au décodeur ESPHome)
    if data.check & 1:
        timings.append(BIT_ONE_HIGH_US)
    else:
        timings.append(BIT_ZERO_HIGH_US)

    return timings


def decode_dooya(timings: list[int]) -> DooyaData | None:
    """Décode une liste de timings OOK en données Dooya.

    Utilisé par le mode apprentissage pour extraire l'ID d'une télécommande.

    Args:
        timings: liste de timings en µs alternant HIGH/LOW

    Returns:
        DooyaData si la trame est valide, None sinon.
    """
    TOLERANCE = 0.35  # 35% de tolérance sur les timings

    def _match(value: int, reference: int) -> bool:
        return abs(value - reference) <= reference * TOLERANCE

    pos = [0]  # liste pour permettre la mutation depuis les closures

    def _read() -> int | None:
        if pos[0] >= len(timings):
            return None
        val = timings[pos[0]]
        pos[0] += 1
        return val

    def _expect_item(high_ref: int, low_ref: int) -> bool:
        h = _read()
        lo = _read()
        if h is None or lo is None:
            return False
        return _match(h, high_ref) and _match(lo, low_ref)

    def _read_bits(nbits: int) -> int | None:
        value = 0
        for _ in range(nbits):
            h = timings[pos[0]] if pos[0] < len(timings) else None
            lo = timings[pos[0] + 1] if pos[0] + 1 < len(timings) else None
            if h is None or lo is None:
                return None
            if _match(h, BIT_ONE_HIGH_US) and _match(lo, BIT_ONE_LOW_US):
                value = (value << 1) | 1
                pos[0] += 2
            elif _match(h, BIT_ZERO_HIGH_US) and _match(lo, BIT_ZERO_LOW_US):
                value = (value << 1) | 0
                pos[0] += 2
            else:
                return None
        return value

    # Header
    if not _expect_item(HEADER_HIGH_US, HEADER_LOW_US):
        return None

    # id (24 bits)
    id_val = _read_bits(24)
    if id_val is None:
        return None

    # channel (8 bits)
    channel_val = _read_bits(8)
    if channel_val is None:
        return None

    # button (4 bits)
    button_val = _read_bits(4)
    if button_val is None:
        return None

    # check (3 bits complets + 1 mark)
    check_val = _read_bits(3)
    if check_val is None:
        return None
    # Dernier bit : mark uniquement
    h = _read()
    if h is None:
        return None
    if _match(h, BIT_ONE_HIGH_US):
        check_val = (check_val << 1) | 1
    elif _match(h, BIT_ZERO_HIGH_US):
        check_val = (check_val << 1) | 0
    else:
        return None

    return DooyaData(id=id_val, channel=channel_val, button=button_val, check=check_val)
