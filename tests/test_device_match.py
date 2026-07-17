"""Tests for the pure ESPHome device-identifier matching helper."""

from device_match import is_esphome_device


class TestIsEsphomeDevice:
    def test_standard_identifier_matches(self):
        assert is_esphome_device({("esphome", "aabbcc")})

    def test_other_domain_does_not_match(self):
        assert not is_esphome_device({("zwave_js", "node-3")})

    def test_three_element_identifier_is_skipped_not_fatal(self):
        # Some integrations store off-spec (domain, x, y) identifiers; they
        # must be ignored, not crash entity setup (0.6.x regression where
        # every Dooya entity failed to load with "ValueError: too many
        # values to unpack").
        assert not is_esphome_device({("some_integration", "a", "b")})

    def test_one_element_identifier_is_skipped(self):
        assert not is_esphome_device({("some_integration",)})

    def test_esphome_found_among_malformed_identifiers(self):
        assert is_esphome_device({("weird", "a", "b"), ("esphome", "gw")})

    def test_empty_identifiers(self):
        assert not is_esphome_device(set())
