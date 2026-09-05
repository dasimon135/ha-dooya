"""The bundled card must be themeable.

Checked on the shipped file so it cannot regress silently:

1. The card renders inside a real ``<ha-card>`` — anything a theme or card-mod
   applies to the card element selects ``ha-card``.

2. No frozen chrome colour. Every colour literal must be the fallback of a
   ``var(--dooya-*, …)`` (or of a Home Assistant variable). The one deliberate
   exception is the window scene — sky, sun, hills, moon, stars — which is an
   illustration of the time of day, not chrome; it is fenced by ``/* scene */``
   … ``/* /scene */`` comments in the stylesheet and skipped here.
"""

from pathlib import Path
import re

CARD = (
    Path(__file__).parents[1]
    / "custom_components"
    / "dooya"
    / "frontend"
    / "dooya-cover-card.js"
)

HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
FALLBACK = re.compile(
    r"var\(\s*--[a-z0-9-]+\s*,\s*(?:var\([^)]*,\s*)?#[0-9a-fA-F]{3,8}\b"
)
SCENE_START, SCENE_END = "/* scene:", "/* /scene */"


def _chrome_lines() -> list[tuple[int, str]]:
    """Source lines that are chrome: outside the scene fence, not the console banner."""
    out: list[tuple[int, str]] = []
    in_scene = False
    for n, line in enumerate(CARD.read_text(encoding="utf-8").splitlines(), 1):
        if SCENE_START in line:
            in_scene = True
            continue
        if SCENE_END in line:
            in_scene = False
            continue
        if in_scene or "console.info" in line:
            continue
        out.append((n, line))
    return out


def test_card_container_is_a_real_ha_card() -> None:
    src = CARD.read_text(encoding="utf-8")
    assert 'document.createElement("ha-card")' in src


def test_scene_fence_is_present_and_balanced() -> None:
    src = CARD.read_text(encoding="utf-8")
    assert src.count(SCENE_START) == 1 and src.count(SCENE_END) == 1
    assert src.index(SCENE_START) < src.index(SCENE_END)


def test_every_chrome_colour_literal_is_a_variable_fallback() -> None:
    frozen = []
    for n, line in _chrome_lines():
        literals = HEX.findall(line)
        if literals and len(FALLBACK.findall(line)) < len(literals):
            frozen.append(f"{n}: {line.strip()[:100]}")
    assert not frozen, (
        "hard-coded chrome colours (not a var() fallback):\n" + "\n".join(frozen)
    )


def test_no_coloured_rgb_literals_in_chrome() -> None:
    """rgba() literals in chrome are tolerated only for pure black shadows/scrims."""
    bad = []
    for n, line in _chrome_lines():
        for m in re.finditer(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", line):
            if m.groups() != ("0", "0", "0"):
                bad.append(f"{n}: {m.group(0)}")
    assert not bad, "coloured rgb() literals in chrome:\n" + "\n".join(bad)
