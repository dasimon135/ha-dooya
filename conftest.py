"""Pytest configuration: import dooya_protocol directly, without Home Assistant."""

import os
import sys

# Put the component directory on the path so the unit tests that need no
# Home Assistant at all can import its pure modules directly.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "custom_components", "dooya"))
