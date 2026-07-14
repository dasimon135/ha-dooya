"""Tests for the TX echo filter (pure Python, no HA dependency)."""

from __future__ import annotations

from echo_filter import TxEchoFilter


class TestTxEchoFilter:
    def test_no_recorded_tx_is_not_echo(self) -> None:
        f = TxEchoFilter(window_seconds=2.0)
        assert not f.is_echo(button=1, now=100.0)

    def test_frame_within_window_is_echo(self) -> None:
        f = TxEchoFilter(window_seconds=2.0)
        f.record_tx(button=1, now=100.0)
        assert f.is_echo(button=1, now=101.5)

    def test_frame_at_exact_window_boundary_is_echo(self) -> None:
        f = TxEchoFilter(window_seconds=2.0)
        f.record_tx(button=1, now=100.0)
        assert f.is_echo(button=1, now=102.0)

    def test_frame_after_window_is_not_echo(self) -> None:
        f = TxEchoFilter(window_seconds=2.0)
        f.record_tx(button=1, now=100.0)
        assert not f.is_echo(button=1, now=102.1)

    def test_different_button_is_not_echo(self) -> None:
        f = TxEchoFilter(window_seconds=2.0)
        f.record_tx(button=1, now=100.0)
        assert not f.is_echo(button=3, now=100.5)

    def test_buttons_tracked_independently(self) -> None:
        f = TxEchoFilter(window_seconds=2.0)
        f.record_tx(button=1, now=100.0)
        f.record_tx(button=5, now=105.0)
        assert not f.is_echo(button=1, now=105.5)
        assert f.is_echo(button=5, now=105.5)

    def test_record_tx_slides_the_window(self) -> None:
        f = TxEchoFilter(window_seconds=2.0)
        f.record_tx(button=1, now=100.0)
        f.record_tx(button=1, now=101.0)
        assert f.is_echo(button=1, now=102.9)

    def test_custom_window(self) -> None:
        f = TxEchoFilter(window_seconds=0.5)
        f.record_tx(button=1, now=100.0)
        assert f.is_echo(button=1, now=100.4)
        assert not f.is_echo(button=1, now=100.6)

    def test_clock_going_backwards_is_not_echo(self) -> None:
        # monotonic() cannot go backwards, but guard against misuse anyway
        f = TxEchoFilter(window_seconds=2.0)
        f.record_tx(button=1, now=100.0)
        assert not f.is_echo(button=1, now=99.0)
