"""Tests for the dooya_protocol module."""

from __future__ import annotations

from dooya_protocol import (
    BIT_ONE_HIGH_US,
    BIT_ONE_LOW_US,
    BIT_ZERO_HIGH_US,
    BIT_ZERO_LOW_US,
    BUTTON_DOWN,
    BUTTON_LED,
    BUTTON_STOP,
    BUTTON_UP,
    HEADER_HIGH_US,
    HEADER_LOW_US,
    DooyaData,
    check_for_button,
    decode_dooya,
    encode_dooya,
    is_frame_consistent,
)
import pytest

# Ids taken from a real ESPHome configuration
VOLET_SALON_GAUCHE = DooyaData(id=0x00D1C917, channel=5, button=BUTTON_UP, check=1)
VOLET_SALON_DROIT = DooyaData(id=0x009BC92B, channel=5, button=BUTTON_UP, check=1)
VOLET_CUISINE = DooyaData(id=0x009CC99F, channel=5, button=BUTTON_UP, check=1)


class TestEncodeDooya:
    """Encoding of Dooya frames."""

    def test_header_present(self) -> None:
        """The header must come first in the frame."""
        timings = encode_dooya(VOLET_SALON_GAUCHE)
        assert timings[0] == HEADER_HIGH_US
        assert timings[1] == HEADER_LOW_US

    def test_frame_length(self) -> None:
        """Expected length: 1 header + 24+8+4+4 bits = 41 items.

        Each bit is 2 timings (high + low), except the last check bit which is
        a mark only: 2 + (24+8+4)*2 + (3*2+1) = 2 + 72 + 7 = 81 timings.
        """
        timings = encode_dooya(VOLET_SALON_GAUCHE)
        assert len(timings) == 81

    def test_bit_one_encoding(self) -> None:
        """A 1 bit must be encoded as HIGH=750µs, LOW=350µs."""
        # channel=5 = 0b00000101, so bits 2 and 0 are set.
        # We only assert that BIT_ONE items appear in the frame.
        timings = encode_dooya(VOLET_SALON_GAUCHE)
        pairs = [(timings[i], timings[i + 1]) for i in range(2, len(timings) - 1, 2)]
        assert (BIT_ONE_HIGH_US, BIT_ONE_LOW_US) in pairs
        assert (BIT_ZERO_HIGH_US, BIT_ZERO_LOW_US) in pairs

    def test_all_buttons_encode(self) -> None:
        """Every button must encode without raising."""
        for button, check in [
            (BUTTON_UP, 1),
            (BUTTON_DOWN, 3),
            (BUTTON_STOP, 5),
            (BUTTON_LED, 15),
        ]:
            data = DooyaData(id=0x00D1C917, channel=5, button=button, check=check)
            timings = encode_dooya(data)
            assert len(timings) == 81

    def test_different_ids_produce_different_timings(self) -> None:
        """Two different ids must produce different frames."""
        t1 = encode_dooya(VOLET_SALON_GAUCHE)
        t2 = encode_dooya(VOLET_SALON_DROIT)
        assert t1 != t2


class TestCheckForButton:
    """Check nibble lookup, per button code."""

    @pytest.mark.parametrize(
        ("button", "expected_check"),
        [
            (BUTTON_UP, 1),
            (BUTTON_DOWN, 3),
            (BUTTON_STOP, 5),
            (BUTTON_LED, 15),
        ],
    )
    def test_known_buttons(self, button: int, expected_check: int) -> None:
        """UP/DOWN/STOP repeat their code; LED does not (issue #14)."""
        assert check_for_button(button) == expected_check

    def test_unknown_button_repeats_itself(self) -> None:
        """A button code outside the table falls back to the old rule."""
        assert check_for_button(9) == 9


class TestFrameConsistency:
    """The check nibble read as an integrity field (issue #19)."""

    @pytest.mark.parametrize(
        ("button", "check"),
        [(BUTTON_UP, 1), (BUTTON_DOWN, 3), (BUTTON_STOP, 5), (BUTTON_LED, 15)],
    )
    def test_a_well_formed_frame_passes(self, button: int, check: int) -> None:
        """Every button a remote really sends is consistent with its check."""
        assert is_frame_consistent(button, check)

    @pytest.mark.parametrize(
        ("button", "check"),
        [
            # Straight from the node log on issue #19: one press of UP, read
            # three times, twice with a check of 15.
            (BUTTON_UP, 15),
            # The dangerous flips: UP is one bit away from DOWN and from STOP,
            # and such a frame keeps the check of the button really pressed.
            (BUTTON_DOWN, 1),
            (BUTTON_STOP, 1),
        ],
    )
    def test_a_mis_decoded_frame_fails(self, button: int, check: int) -> None:
        """A bit read wrong leaves button and check disagreeing."""
        assert not is_frame_consistent(button, check)


class TestDecodeDooya:
    """Decoding of Dooya frames."""

    def test_roundtrip_salon_gauche(self) -> None:
        """Encoding then decoding must return the original fields."""
        original = VOLET_SALON_GAUCHE
        timings = encode_dooya(original)
        decoded = decode_dooya(timings)
        assert decoded is not None
        assert decoded.id == original.id
        assert decoded.channel == original.channel
        assert decoded.button == original.button
        assert decoded.check == original.check

    def test_roundtrip_cuisine(self) -> None:
        """Roundtrip for the kitchen shutter."""
        original = VOLET_CUISINE
        timings = encode_dooya(original)
        decoded = decode_dooya(timings)
        assert decoded is not None
        assert decoded.id == original.id

    def test_invalid_header_returns_none(self) -> None:
        """A frame with a bad header must decode to None."""
        bad_timings = [100, 100] + [350, 750] * 40
        result = decode_dooya(bad_timings)
        assert result is None

    def test_empty_returns_none(self) -> None:
        """An empty list must decode to None."""
        assert decode_dooya([]) is None

    @pytest.mark.parametrize(
        "volet",
        [
            DooyaData(id=0x00D1C917, channel=5, button=BUTTON_UP, check=1),
            DooyaData(id=0x009BC92B, channel=5, button=BUTTON_DOWN, check=3),
            DooyaData(id=0x009CC99F, channel=5, button=BUTTON_STOP, check=5),
            DooyaData(id=0x00C9C9D4, channel=5, button=BUTTON_UP, check=1),
            DooyaData(id=0x00D9C95A, channel=5, button=BUTTON_UP, check=1),
            DooyaData(id=0x001589D1, channel=5, button=BUTTON_LED, check=15),
        ],
    )
    def test_roundtrip_parametrized(self, volet: DooyaData) -> None:
        """Roundtrip across several shutters of one configuration."""
        timings = encode_dooya(volet)
        decoded = decode_dooya(timings)
        assert decoded is not None
        assert decoded.id == volet.id
        assert decoded.channel == volet.channel
        assert decoded.button == volet.button
        assert decoded.check == volet.check
