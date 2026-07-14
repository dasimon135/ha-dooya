"""Tests for the pure position-estimation math (travel_calc)."""

import pytest

from travel_calc import clamp_position, position_after, travel_duration


class TestClampPosition:
    def test_within_range(self):
        assert clamp_position(42) == 42

    def test_below_zero(self):
        assert clamp_position(-3) == 0

    def test_above_hundred(self):
        assert clamp_position(150.2) == 100

    def test_rounds_floats(self):
        assert clamp_position(49.6) == 50
        assert clamp_position(49.4) == 49


class TestPositionAfter:
    def test_opening_mid_travel(self):
        # From 0, opening with 20 s full travel: after 5 s -> 25 %
        assert position_after(0, 1, 5.0, 20.0, 100) == 25

    def test_closing_mid_travel(self):
        # From 100, closing with 10 s full travel: after 2.5 s -> 75 %
        assert position_after(100, -1, 2.5, 10.0, 0) == 75

    def test_opening_capped_at_target(self):
        # Partial move up to 50 must not overshoot the target
        assert position_after(0, 1, 15.0, 20.0, 50) == 50

    def test_closing_capped_at_target(self):
        assert position_after(100, -1, 15.0, 20.0, 40) == 40

    def test_full_open_when_elapsed_exceeds_travel(self):
        assert position_after(0, 1, 25.0, 20.0, 100) == 100

    def test_full_close_when_elapsed_exceeds_travel(self):
        assert position_after(80, -1, 25.0, 20.0, 0) == 0

    def test_asymmetric_travel_times(self):
        # 30 s down travel: from 90, closing for 3 s -> 90 - 10 = 80
        assert position_after(90, -1, 3.0, 30.0, 0) == 80

    def test_zero_elapsed_keeps_start(self):
        assert position_after(37, 1, 0.0, 20.0, 100) == 37

    def test_invalid_travel_time_returns_start(self):
        # A zero/negative travel time must not divide by zero
        assert position_after(40, 1, 5.0, 0.0, 100) == 40
        assert position_after(40, -1, 5.0, -2.0, 0) == 40


class TestTravelDuration:
    def test_full_travel(self):
        assert travel_duration(100, 20.0) == pytest.approx(20.0)

    def test_half_travel(self):
        assert travel_duration(50, 20.0) == pytest.approx(10.0)

    def test_zero_distance(self):
        assert travel_duration(0, 20.0) == 0.0

    def test_invalid_travel_time(self):
        assert travel_duration(50, 0.0) == 0.0
