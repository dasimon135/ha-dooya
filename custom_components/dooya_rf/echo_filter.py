"""Filter that suppresses RF frames echoing our own transmissions.

With several ESP32 nodes in the house, a node in RX mode hears the frames
transmitted by another node and reports them through the same
`esphome.dooya_received` event as a genuine remote press. Treating such an
echo as a remote press would cancel the delayed STOP scheduled by
`set_position` and send the shutter to its hard limit.

Pure Python on purpose: unit-tested without Home Assistant, like
`dooya_protocol`.
"""

from __future__ import annotations


class TxEchoFilter:
    """Remember recent own transmissions per button and flag their echoes.

    Only the same button is suppressed: a genuine press of the opposite
    button during the window must still get through.
    """

    def __init__(self, window_seconds: float = 2.0) -> None:
        """Initialize the filter with the suppression window in seconds."""
        self._window = window_seconds
        self._last_tx: dict[int, float] = {}

    def record_tx(self, button: int, now: float) -> None:
        """Record that we just transmitted this button at time `now`."""
        self._last_tx[button] = now

    def is_echo(self, button: int, now: float) -> bool:
        """Return True if a frame for `button` at `now` echoes our own TX."""
        last = self._last_tx.get(button)
        if last is None:
            return False
        return 0 <= (now - last) <= self._window
