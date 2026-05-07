"""Tests pour le module dooya_protocol."""

from __future__ import annotations

import pytest

from dooya_protocol import (
    BUTTON_DOWN,
    BUTTON_STOP,
    BUTTON_UP,
    HEADER_HIGH_US,
    HEADER_LOW_US,
    BIT_ONE_HIGH_US,
    BIT_ONE_LOW_US,
    BIT_ZERO_HIGH_US,
    BIT_ZERO_LOW_US,
    DooyaData,
    decode_dooya,
    encode_dooya,
)

# IDs tirés de la configuration ESPHome de l'utilisateur
VOLET_SALON_GAUCHE = DooyaData(id=0x00D1C917, channel=5, button=BUTTON_UP, check=1)
VOLET_SALON_DROIT = DooyaData(id=0x009BC92B, channel=5, button=BUTTON_UP, check=1)
VOLET_CUISINE = DooyaData(id=0x009CC99F, channel=5, button=BUTTON_UP, check=1)


class TestEncodeDooya:
    """Tests d'encodage de trames Dooya."""

    def test_header_present(self) -> None:
        """Le header doit être en tête de trame."""
        timings = encode_dooya(VOLET_SALON_GAUCHE)
        assert timings[0] == HEADER_HIGH_US
        assert timings[1] == HEADER_LOW_US

    def test_frame_length(self) -> None:
        """Longueur attendue : 1 header + 24+8+4+4 bits = 41 éléments.
        
        Chaque bit = 2 timings (high + low), sauf le dernier bit du check = 1 timing.
        Total : 2 + (24+8+4)*2 + (3*2+1) = 2 + 72 + 7 = 81 timings.
        """
        timings = encode_dooya(VOLET_SALON_GAUCHE)
        assert len(timings) == 81

    def test_bit_one_encoding(self) -> None:
        """Un bit 1 doit être encodé HIGH=750µs, LOW=350µs."""
        # channel=5 = 0b00000101 → bits 0 sont à 0, bits 2 et 0 sont à 1
        # On vérifie juste qu'on retrouve des BIT_ONE dans la trame
        timings = encode_dooya(VOLET_SALON_GAUCHE)
        pairs = [(timings[i], timings[i + 1]) for i in range(2, len(timings) - 1, 2)]
        assert (BIT_ONE_HIGH_US, BIT_ONE_LOW_US) in pairs
        assert (BIT_ZERO_HIGH_US, BIT_ZERO_LOW_US) in pairs

    def test_all_buttons_encode(self) -> None:
        """Chaque bouton doit produire une trame sans exception."""
        for button, check in [
            (BUTTON_UP, 1),
            (BUTTON_DOWN, 3),
            (BUTTON_STOP, 5),
        ]:
            data = DooyaData(id=0x00D1C917, channel=5, button=button, check=check)
            timings = encode_dooya(data)
            assert len(timings) == 81

    def test_different_ids_produce_different_timings(self) -> None:
        """Deux IDs différents doivent produire des trames différentes."""
        t1 = encode_dooya(VOLET_SALON_GAUCHE)
        t2 = encode_dooya(VOLET_SALON_DROIT)
        assert t1 != t2


class TestDecodeDooya:
    """Tests de décodage de trames Dooya."""

    def test_roundtrip_salon_gauche(self) -> None:
        """Encoder puis décoder doit retrouver les données originales."""
        original = VOLET_SALON_GAUCHE
        timings = encode_dooya(original)
        decoded = decode_dooya(timings)
        assert decoded is not None
        assert decoded.id == original.id
        assert decoded.channel == original.channel
        assert decoded.button == original.button
        assert decoded.check == original.check

    def test_roundtrip_cuisine(self) -> None:
        """Roundtrip pour le volet cuisine."""
        original = VOLET_CUISINE
        timings = encode_dooya(original)
        decoded = decode_dooya(timings)
        assert decoded is not None
        assert decoded.id == original.id

    def test_invalid_header_returns_none(self) -> None:
        """Une trame avec un mauvais header doit retourner None."""
        bad_timings = [100, 100] + [350, 750] * 40
        result = decode_dooya(bad_timings)
        assert result is None

    def test_empty_returns_none(self) -> None:
        """Une liste vide doit retourner None."""
        assert decode_dooya([]) is None

    @pytest.mark.parametrize(
        "volet",
        [
            DooyaData(id=0x00D1C917, channel=5, button=BUTTON_UP, check=1),
            DooyaData(id=0x009BC92B, channel=5, button=BUTTON_DOWN, check=3),
            DooyaData(id=0x009CC99F, channel=5, button=BUTTON_STOP, check=5),
            DooyaData(id=0x00C9C9D4, channel=5, button=BUTTON_UP, check=1),
            DooyaData(id=0x00D9C95A, channel=5, button=BUTTON_UP, check=1),
        ],
    )
    def test_roundtrip_parametrized(self, volet: DooyaData) -> None:
        """Roundtrip pour plusieurs volets de la configuration."""
        timings = encode_dooya(volet)
        decoded = decode_dooya(timings)
        assert decoded is not None
        assert decoded.id == volet.id
        assert decoded.channel == volet.channel
        assert decoded.button == volet.button
        assert decoded.check == volet.check
