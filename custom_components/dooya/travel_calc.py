"""Pure position-estimation math for time-based cover travel.

No Home Assistant imports — this module is unit-tested directly.
"""

from __future__ import annotations


def clamp_position(value: float | int) -> int:
    """Clamp a position into the 0..100 range, rounded to an int."""
    return max(0, min(100, round(float(value))))


def position_after(
    start: float,
    direction: int,
    elapsed: float,
    travel_time: float,
    target: int,
) -> int:
    """Estimated position after moving for `elapsed` seconds.

    Args:
        start: position when the movement began (0..100)
        direction: +1 opening, -1 closing
        elapsed: seconds since the movement began
        travel_time: full-travel duration in seconds for this direction
        target: position the movement is heading to (caps the result)

    Returns:
        The estimated position, clamped to 0..100 and capped at `target`.
    """
    if travel_time <= 0:
        return clamp_position(start)

    delta = (elapsed / travel_time) * 100
    current = start + direction * delta

    if direction > 0:
        current = min(current, target)
    else:
        current = max(current, target)

    return clamp_position(current)


def travel_duration(distance: float, travel_time: float) -> float:
    """Seconds needed to travel `distance` % at the given full-travel time."""
    if travel_time <= 0 or distance <= 0:
        return 0.0
    return (distance / 100) * travel_time
