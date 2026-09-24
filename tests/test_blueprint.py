"""Structure of the sun blueprint (pure Python, no HA dependency).

Parses the YAML only: this does not run the blueprint in Home Assistant.
"""

from __future__ import annotations

from pathlib import Path

import yaml

BLUEPRINT = (
    Path(__file__).parent.parent
    / "blueprints"
    / "automation"
    / "dooya"
    / "shutters_sun.yaml"
)


class _Input(str):
    """Stand-in for a `!input name` tag."""


class _Loader(yaml.SafeLoader):
    """Safe loader that accepts the blueprint's `!input` tag."""


_Loader.add_constructor(
    "!input", lambda loader, node: _Input(loader.construct_scalar(node))
)


def _load() -> dict:
    with BLUEPRINT.open(encoding="utf-8") as handle:
        return yaml.load(handle, Loader=_Loader)


def _morning_branch(blueprint: dict) -> list[dict]:
    for option in blueprint["actions"][0]["choose"]:
        conditions = option["conditions"]
        if {"condition": "trigger", "id": "morning"} in conditions:
            return conditions
    raise AssertionError("no morning branch")


def test_morning_fires_at_the_earliest_time_too() -> None:
    """A sun rising before the earliest time still opens at that time."""
    morning = [t for t in _load()["triggers"] if t.get("id") == "morning"]

    assert {"trigger": "time", "at": "earliest_open", "id": "morning"} in morning
    assert any(t["trigger"] == "numeric_state" for t in morning)


def test_morning_opens_only_with_the_sun_up() -> None:
    """The time trigger alone must not open before the sun is high enough."""
    conditions = _morning_branch(_load())

    assert {
        "condition": "numeric_state",
        "entity_id": "sun.sun",
        "attribute": "elevation",
        "above": "morning_elevation",
    } in conditions
    assert {"condition": "time", "after": "earliest_open"} in conditions
