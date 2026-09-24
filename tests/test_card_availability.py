"""The card follows the cover's availability and its supported features.

Since v0.12.0 a cover follows its ESPHome gateway's availability, so an offline
gateway leaves the cover `unavailable`: the card must say so and offer no live
control, in every layout. The group cover (the remote's common button) has no
SET_POSITION (bit 4 of `supported_features`): the card must not offer a slider,
position presets, a favorite, a recalibration or a tap-to-position, since every
one of those would fail or do nothing. Open, stop and close stay.

These run the shipped card under Node (``tests/card_harness.js``) and are
skipped when Node is not installed.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest

NODE = shutil.which("node")
HARNESS = Path(__file__).with_name("card_harness.js")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

ENTITY = "cover.salon"
FAVORITE = "button.salon_favorite"
LAYOUTS = ("full", "compact", "tile")

# OPEN | CLOSE | STOP, what the group cover exposes; 15 adds SET_POSITION.
NO_POSITION = 1 | 2 | 8
FULL_FEATURES = NO_POSITION | 4


def _run(
    state: str = "open",
    *,
    features: int | None = FULL_FEATURES,
    position: int | None = 60,
    layout: str = "full",
    language: str = "en",
    click: dict | None = None,
    device_class: str | None = None,
) -> dict:
    attributes: dict = {"friendly_name": "Salon"}
    if device_class:
        attributes["device_class"] = device_class
    if position is not None:
        attributes["current_position"] = position
    if features is not None:
        attributes["supported_features"] = features
    scenario: dict = {
        "config": {"entity": ENTITY, "layout": layout},
        "state": {"state": state, "attributes": attributes},
        "language": language,
        # A favorite button on the same device, so the star is drawn when it may be.
        "entities": {
            FAVORITE: {
                "platform": "dooya",
                "device_id": "dev1",
                "unique_id": "entry1_favorite",
            }
        },
    }
    if click:
        scenario["click"] = click
    out = subprocess.run(
        [NODE, str(HARNESS), json.dumps(scenario)],
        capture_output=True,
        text=True,
        # Node writes UTF-8; Windows would otherwise decode it as cp1252.
        encoding="utf-8",
        check=True,
        timeout=30,
    )
    return json.loads(out.stdout)


def _controls(html: str) -> list[str]:
    """Every button and input tag the card drew."""
    return re.findall(r"<(?:button|input)\b[^>]*>", html)


# ---- an unavailable cover -------------------------------------------------


@pytest.mark.parametrize("layout", LAYOUTS)
def test_an_unavailable_cover_says_so(layout: str) -> None:
    html = _run("unavailable", position=None, layout=layout)["html"]

    assert "Unavailable" in html


def test_the_unavailable_label_is_translated() -> None:
    html = _run("unavailable", position=None, language="fr")["html"]

    assert "Indisponible" in html


@pytest.mark.parametrize("layout", LAYOUTS)
def test_an_unavailable_cover_disables_every_control(layout: str) -> None:
    html = _run("unavailable", position=None, layout=layout)["html"]
    controls = _controls(html)

    assert controls, layout
    assert all(re.search(r"\sdisabled\b", c) for c in controls), controls


def test_an_unavailable_shutter_is_not_drawn_open() -> None:
    """No position means an open window before: that read as `open`."""
    html = _run("unavailable", position=None)["html"]

    assert 'style="height:0%"' not in html


@pytest.mark.parametrize(
    "click",
    [
        {"selector": "data-act", "value": "open"},
        {"selector": "data-act", "value": "close"},
        {"selector": "data-act", "value": "stop"},
        {"selector": "data-pos", "value": 50},
        {"selector": "data-window", "clientY": 30},
    ],
    ids=["open", "close", "stop", "preset", "window"],
)
def test_an_unavailable_cover_sends_nothing(click: dict) -> None:
    assert _run("unavailable", position=None, click=click)["calls"] == []


# ---- a cover without SET_POSITION (the group cover) -----------------------


def test_no_position_feature_means_no_slider_presets_or_favorite() -> None:
    html = _run("unknown", features=NO_POSITION, position=None)["html"]

    assert "data-slider" not in html
    assert "data-pos=" not in html
    assert "data-fav=" not in html
    assert 'data-act="mark_open"' not in html
    assert 'data-act="mark_closed"' not in html


@pytest.mark.parametrize("layout", LAYOUTS)
def test_no_position_feature_keeps_open_stop_close(layout: str) -> None:
    html = _run("unknown", features=NO_POSITION, position=None, layout=layout)["html"]

    for act in ("open", "stop", "close"):
        assert f'data-act="{act}"' in html, (layout, act)
    assert "disabled" not in html, layout


def test_no_position_feature_means_no_position_bar_in_compact() -> None:
    html = _run("unknown", features=NO_POSITION, position=None, layout="compact")[
        "html"
    ]

    assert "data-bar" not in html
    assert "data-fav=" not in html


@pytest.mark.parametrize(
    "click",
    [
        {"selector": "data-window", "clientY": 30},
        {"selector": "data-pos", "value": 50},
    ],
    ids=["window", "preset"],
)
def test_no_position_feature_sends_no_position(click: dict) -> None:
    calls = _run("unknown", features=NO_POSITION, position=None, click=click)["calls"]

    assert calls == []


def test_no_position_feature_still_opens() -> None:
    click = {"selector": "data-act", "value": "open"}
    calls = _run("unknown", features=NO_POSITION, position=None, click=click)["calls"]

    assert calls == [
        {"domain": "cover", "service": "open_cover", "data": {"entity_id": ENTITY}}
    ]


# ---- a normal cover is unchanged ------------------------------------------


def test_a_full_featured_cover_keeps_every_control() -> None:
    html = _run()["html"]

    assert "data-slider" in html
    assert 'data-pos="50"' in html
    assert f'data-fav="{FAVORITE}"' in html
    assert 'data-act="mark_open"' in html
    assert "disabled" not in html
    assert "data-bar" in _run(layout="compact")["html"]


def test_a_full_featured_cover_still_sets_a_position_from_the_window() -> None:
    calls = _run(click={"selector": "data-window", "clientY": 30})["calls"]

    assert calls == [
        {
            "domain": "cover",
            "service": "set_cover_position",
            "data": {"entity_id": ENTITY, "position": 70},
        }
    ]


def test_an_unknown_state_is_not_treated_as_unavailable() -> None:
    """The group cover is always `unknown`: it has no position to report.

    Disabling its controls on `unknown` would make the remote's common button
    unusable from the card.
    """
    html = _run("unknown", position=None)["html"]

    assert "Unavailable" not in html
    assert "disabled" not in html


# ---- a cover that knows no state (the group cover) ------------------------


def _state_word(html: str) -> str:
    """The text of the state label, whatever the layout."""
    m = re.search(r'<(?:div class="state[^"]*"[^>]*|span class="tsub")>([^<]*)<', html)
    assert m, html
    return m.group(1)


def _window_classes(html: str) -> str:
    m = re.search(r'<div class="(window[^"]*)"', html)
    assert m, html
    return m.group(1)


@pytest.mark.parametrize("layout", LAYOUTS)
def test_the_group_cover_claims_no_state(layout: str) -> None:
    html = _run("unknown", features=NO_POSITION, position=None, layout=layout)["html"]

    assert _state_word(html) == "", layout


def test_the_group_shutter_is_drawn_half_way_not_greyed() -> None:
    html = _run("unknown", features=NO_POSITION, position=None)["html"]

    assert 'style="height:50%"' in html
    assert "off" not in _window_classes(html).split()


def test_the_group_awning_is_drawn_half_deployed_not_greyed() -> None:
    html = _run("unknown", features=NO_POSITION, position=None, device_class="awning")[
        "html"
    ]

    assert "aw-stripe" in html
    assert "off" not in _window_classes(html).split()


def test_the_group_tile_shows_the_closed_icon() -> None:
    html = _run("unknown", features=NO_POSITION, position=None, layout="tile")["html"]

    assert 'icon="mdi:window-shutter"' in html
    assert "mdi:window-shutter-open" not in html


def test_a_cover_with_a_known_state_but_no_position_keeps_its_word() -> None:
    html = _run("closed", features=NO_POSITION, position=None)["html"]

    assert _state_word(html) == "Closed"
