"""Tell one press of the physical remote from the frames that carry it.

A Dooya remote sends each press as a burst of identical frames a few ms
apart, and keeps sending while the button is held. Two receiving nodes, or a
node repeating the press, add more copies. The cover can act on every frame
(it only restarts the same estimate), but the remote's event entity must fire
once per press, or an automation on "down" would run three times.

Pure Python on purpose: unit-tested without Home Assistant, like
`echo_filter`.
"""

from __future__ import annotations

# Frames of one burst are a few ms apart and a held button repeats them
# without pause. Two presses of the same button closer than this count as one.
PRESS_GAP_SEC = 1.0


class PressTracker:
    """Flag the first frame of each press, per button."""

    def __init__(self, gap_seconds: float = PRESS_GAP_SEC) -> None:
        """Initialize the tracker with the silence that separates two presses."""
        self._gap = gap_seconds
        self._last_frame: dict[int, float] = {}

    def is_new_press(self, button: int, now: float) -> bool:
        """Record a frame of `button` at `now`; True if it starts a new press.

        Every frame moves the reference forward, so a held button, which
        never leaves a gap, stays a single press however long it lasts.
        """
        last = self._last_frame.get(button)
        self._last_frame[button] = now
        return last is None or not 0 <= now - last <= self._gap
