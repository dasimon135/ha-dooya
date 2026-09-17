"""The card's size option is called `layout`, and `view` still works.

`layout: full | compact | tile` is the name the other cards in this family use
(madoka, rf-fan), and `view` was this card's own spelling of the same idea. A
dashboard written against `view` must keep working for good — including
`view: normal`, the old name of `full` — so both are read, and `layout` wins
when a config carries both.

These run the shipped card under Node (``tests/card_harness.js``) and are
skipped when Node is not installed. They need no Home Assistant harness, so
they also run on Windows.
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

TILE_MARKER = 'data-act="tileinfo"'
COMPACT_MARKER = '<div class="compact">'
FULL_MARKER = "data-window"


def _node(scenario: dict) -> dict:
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


def _render(**config) -> dict:
    return _node(
        {
            "config": {"entity": ENTITY, **config},
            "state": {
                "state": "open",
                "attributes": {"current_position": 60, "friendly_name": "Terrasse"},
            },
        }
    )


def _editor(config: dict) -> dict:
    return _node({"editor": {"config": config}})


# --- the new name ---------------------------------------------------------


def test_layout_tile_draws_the_tile() -> None:
    assert TILE_MARKER in _render(layout="tile")["html"]


def test_layout_compact_draws_the_bar() -> None:
    assert COMPACT_MARKER in _render(layout="compact")["html"]


def test_layout_full_draws_the_full_card() -> None:
    html = _render(layout="full")["html"]
    assert FULL_MARKER in html
    assert TILE_MARKER not in html


def test_no_layout_at_all_still_draws_the_full_card() -> None:
    assert FULL_MARKER in _render()["html"]


# --- the old name, kept ---------------------------------------------------


def test_view_tile_still_draws_the_tile() -> None:
    assert TILE_MARKER in _render(view="tile")["html"]


def test_view_compact_still_draws_the_bar() -> None:
    assert COMPACT_MARKER in _render(view="compact")["html"]


def test_view_normal_still_draws_the_full_card() -> None:
    assert FULL_MARKER in _render(view="normal")["html"]


def test_layout_wins_when_a_config_carries_both() -> None:
    assert TILE_MARKER in _render(view="normal", layout="tile")["html"]


# --- the height the dashboard reserves ------------------------------------


def test_a_tile_is_one_row_high_under_either_name() -> None:
    assert _render(layout="tile")["size"] == 1
    assert _render(view="tile")["size"] == 1


def test_a_compact_card_is_two_rows_high_under_either_name() -> None:
    assert _render(layout="compact")["size"] == 2
    assert _render(view="compact")["size"] == 2


def test_a_full_card_is_five_rows_high() -> None:
    assert _render(layout="full")["size"] == 5


# --- the visual editor ----------------------------------------------------


def test_the_editor_offers_layout_and_not_view() -> None:
    schema = _editor({"entity": ENTITY})["schema"]
    assert "layout" in schema
    assert "view" not in schema


def test_the_editor_shows_full_when_nothing_is_stored() -> None:
    assert _editor({"entity": ENTITY})["data"]["layout"] == "full"


def test_the_editor_reads_a_stored_view_into_layout() -> None:
    """Opening an old config must not show it as `full` and silently reset it."""
    data = _editor({"entity": ENTITY, "view": "tile"})["data"]
    assert data["layout"] == "tile"


def test_the_editor_translates_the_old_normal_into_full() -> None:
    assert _editor({"entity": ENTITY, "view": "normal"})["data"]["layout"] == "full"


def test_the_editor_drops_view_so_the_two_cannot_disagree() -> None:
    """Whatever the editor writes back must carry one spelling, not both."""
    assert "view" not in _editor({"entity": ENTITY, "view": "compact"})["data"]
