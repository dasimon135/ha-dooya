"""The bundled card draws an awning as an awning (issue #50).

A cover whose device class is `awning` gets a facade scene with a striped
canopy instead of a roller shutter, Home Assistant's own awning control icons
(the ones the tile card uses), and labels that say deployed and retracted.
Shutters are untouched.

These run the shipped card under Node (``tests/card_harness.js``) and are
skipped when Node is not installed. They do not need the Home Assistant
harness, so they also run on Windows.
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

ENTITY = "cover.terrasse"


def _run(
    device_class: str | None,
    position: int,
    *,
    state: str | None = None,
    view: str = "normal",
    language: str = "en",
    click: dict | None = None,
) -> dict:
    attributes: dict = {"current_position": position, "friendly_name": "Terrasse"}
    if device_class:
        attributes["device_class"] = device_class
    scenario = {
        "config": {"entity": ENTITY, "view": view},
        "state": {
            "state": state or ("closed" if position == 0 else "open"),
            "attributes": attributes,
        },
        "language": language,
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


# ---- what an awning looks like -------------------------------------------


def test_an_awning_is_drawn_as_a_canopy_not_a_shutter() -> None:
    html = _run("awning", 60)["html"]

    assert "awning-scene" in html
    assert 'class="curtain' not in html


def test_a_shutter_keeps_its_roller_shutter() -> None:
    html = _run("shutter", 60)["html"]

    assert 'class="curtain' in html
    assert "awning-scene" not in html


def test_a_retracted_awning_shows_no_fabric() -> None:
    assert "aw-stripe" not in _run("awning", 0)["html"]


def test_a_deployed_awning_shows_its_fabric() -> None:
    assert "aw-stripe" in _run("awning", 60)["html"]


def test_the_awning_uses_home_assistant_awning_control_icons() -> None:
    """Same icons as the tile card: frontend src/common/entity/cover_icon.ts."""
    for view in ("normal", "compact", "tile"):
        html = _run("awning", 60, view=view)["html"]
        assert "mdi:arrow-expand-horizontal" in html, view
        assert "mdi:arrow-collapse-horizontal" in html, view
        assert "mdi:chevron-up" not in html, view


def test_a_shutter_keeps_its_up_and_down_arrows() -> None:
    for view in ("normal", "compact", "tile"):
        html = _run("shutter", 60, view=view)["html"]
        assert "mdi:chevron-up" in html, view
        assert "mdi:arrow-expand-horizontal" not in html, view


def test_awning_labels_say_deployed_and_retracted() -> None:
    html = _run("awning", 60)["html"]

    assert "Retracted" in html
    assert "Deployed" in html


def test_awning_labels_are_translated() -> None:
    html = _run("awning", 60, language="fr")["html"]

    assert "Replié" in html
    assert "Déployé" in html


def test_a_moving_awning_says_deploying() -> None:
    html = _run("awning", 40, state="opening")["html"]

    assert "Deploying" in html


# ---- what an awning does when touched ------------------------------------


def test_the_deploy_button_still_opens_the_cover() -> None:
    """Deployed is open in Home Assistant; the integration picks the button."""
    calls = _run("awning", 30, click={"selector": "data-act", "value": "open"})["calls"]

    assert calls == [
        {"domain": "cover", "service": "open_cover", "data": {"entity_id": ENTITY}}
    ]


def test_clicking_low_in_the_awning_scene_deploys_further() -> None:
    """The canopy hangs down as it deploys: low in the picture is more open."""
    low_click = {"selector": "data-window", "clientY": 80}
    calls = _run("awning", 30, click=low_click)["calls"]

    assert calls == [
        {
            "domain": "cover",
            "service": "set_cover_position",
            "data": {"entity_id": ENTITY, "position": 80},
        }
    ]


def test_clicking_low_in_the_shutter_window_still_closes_it() -> None:
    low_click = {"selector": "data-window", "clientY": 80}
    calls = _run("shutter", 30, click=low_click)["calls"]

    assert calls[0]["data"]["position"] == 20
