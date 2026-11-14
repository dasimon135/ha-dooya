"""Tests for the press tracker: one press of the remote, one event.

Pure Python, no Home Assistant: runs everywhere, Windows included.
"""

from __future__ import annotations

from custom_components.dooya_rf.remote_press import PressTracker

UP, DOWN = 1, 3


def test_the_first_frame_is_a_press() -> None:
    assert PressTracker().is_new_press(UP, 10.0)


def test_the_rest_of_a_burst_is_the_same_press() -> None:
    """A remote sends each press as several frames a few ms apart."""
    tracker = PressTracker()
    assert tracker.is_new_press(UP, 10.0)
    assert not tracker.is_new_press(UP, 10.05)
    assert not tracker.is_new_press(UP, 10.10)


def test_a_held_button_stays_one_press() -> None:
    """Each frame restarts the gap, so a long hold never fires twice."""
    tracker = PressTracker(gap_seconds=1.0)
    assert tracker.is_new_press(UP, 10.0)
    for step in range(1, 40):
        assert not tracker.is_new_press(UP, 10.0 + step * 0.1)


def test_a_press_after_a_pause_is_a_new_press() -> None:
    tracker = PressTracker(gap_seconds=1.0)
    assert tracker.is_new_press(UP, 10.0)
    assert tracker.is_new_press(UP, 11.5)


def test_another_button_is_a_new_press_at_once() -> None:
    """Up then down within the gap: both are real presses."""
    tracker = PressTracker()
    assert tracker.is_new_press(UP, 10.0)
    assert tracker.is_new_press(DOWN, 10.2)


def test_a_clock_going_backwards_is_a_new_press() -> None:
    tracker = PressTracker()
    assert tracker.is_new_press(UP, 10.0)
    assert tracker.is_new_press(UP, 5.0)
