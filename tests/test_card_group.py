"""The card on a Home Assistant cover group, and the tile's words.

A cover group (`cover.volets_salon` standing for two shutters) used to show
only the group: no way to move one shutter without leaving the card. The full
card now lists the members, one row each, and each row commands its member.

These run the shipped card under Node (``tests/card_harness.js``) and are
skipped when Node is not installed.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

NODE = shutil.which("node")
HARNESS = Path(__file__).with_name("card_harness.js")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

GROUP = "cover.volets_salon"
LEFT = "cover.salon_gauche"
RIGHT = "cover.salon_droite"


def _node(scenario: dict) -> dict:
    out = subprocess.run(
        [NODE, str(HARNESS), json.dumps(scenario)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=30,
    )
    return json.loads(out.stdout)


def _member(name: str, state: str = "open", position: int | None = 100) -> dict:
    attributes = {"friendly_name": name, "supported_features": 15}
    if position is not None:
        attributes["current_position"] = position
    return {"state": state, "attributes": attributes}


def _group(click: dict | None = None, layout: str = "full", **members) -> dict:
    states = {
        LEFT: members.get("left", _member("Salon gauche")),
        RIGHT: members.get("right", _member("Salon droite", "open", 40)),
    }
    scenario = {
        "config": {"entity": GROUP, "layout": layout},
        "state": {
            "state": "open",
            "attributes": {
                "friendly_name": "Volets Salon",
                "current_position": 70,
                "supported_features": 15,
                "entity_id": [LEFT, RIGHT],
            },
        },
        "states": states,
        # A group is not a dooya_rf entity, and has no device.
        "entities": {GROUP: {"platform": "group"}},
    }
    if click:
        scenario["click"] = click
    return _node(scenario)


# --- the group's members ----------------------------------------------------


def test_the_full_card_lists_every_member() -> None:
    html = _group()["html"]
    assert html.count('class="mrow') == 2
    assert "Salon gauche" in html
    assert "Salon droite" in html
    assert f'data-member="{LEFT}"' in html
    assert f'data-member="{RIGHT}"' in html


def test_a_member_row_says_where_that_member_is() -> None:
    html = _group()["html"]
    # Its own position, not the group's 70 %.
    assert "Open · 40%" in html
    assert "Open · 100%" in html


@pytest.mark.parametrize(
    ("act", "service"),
    [("open", "open_cover"), ("stop", "stop_cover"), ("close", "close_cover")],
)
def test_a_member_button_moves_that_member_alone(act: str, service: str) -> None:
    calls = _group(
        click={"selector": "data-member", "value": {"entity": RIGHT, "act": act}}
    )["calls"]
    assert calls == [
        {"domain": "cover", "service": service, "data": {"entity_id": RIGHT}}
    ]


def test_an_unavailable_member_takes_no_command() -> None:
    result = _group(
        click={"selector": "data-member", "value": {"entity": RIGHT, "act": "open"}},
        right=_member("Salon droite", "unavailable", None),
    )
    assert result["calls"] == []
    assert "Unavailable" in result["html"]


def test_a_click_cannot_command_an_entity_outside_the_group() -> None:
    calls = _group(
        click={
            "selector": "data-member",
            "value": {"entity": "cover.garage", "act": "open"},
        }
    )["calls"]
    assert calls == []


def test_a_single_cover_has_no_member_list() -> None:
    html = _node(
        {
            "config": {"entity": "cover.salon_gauche"},
            "state": _member("Salon gauche", "open", 60),
        }
    )["html"]
    assert "mrow" not in html


def test_the_tile_of_a_group_stays_a_tile() -> None:
    html = _group(layout="tile")["html"]
    assert 'data-act="tileinfo"' in html
    assert "mrow" not in html


# --- the tile's words -------------------------------------------------------


def _tile(state: str, position: int | None, language: str = "en") -> str:
    return _node(
        {
            "config": {"entity": LEFT, "layout": "tile"},
            "state": _member("Salon gauche", state, position),
            "language": language,
        }
    )["html"]


def test_the_tile_gives_the_position_of_an_open_cover() -> None:
    assert '<span class="tsub">Open · 100%</span>' in _tile("open", 100)
    assert '<span class="tsub">Open · 60%</span>' in _tile("open", 60)


def test_the_tile_says_closed_alone() -> None:
    assert '<span class="tsub">Closed</span>' in _tile("closed", 0)


def test_the_tile_uses_the_french_spacing() -> None:
    assert '<span class="tsub">Ouvert · 60 %</span>' in _tile("open", 60, "fr")


def test_a_moving_tile_says_it_moves() -> None:
    assert '<span class="tsub">Opening…</span>' in _tile("opening", 40)


# --- the name ---------------------------------------------------------------


def test_the_name_is_the_friendly_name() -> None:
    html = _tile("open", 60)
    assert '<span class="tname">Salon gauche</span>' in html
