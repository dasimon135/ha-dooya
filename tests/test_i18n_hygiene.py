"""Repository-wide guards against the two i18n defects that keep coming back.

Three separate fixes were needed for the same underlying problem — #22, #26 and
#29 — because each one corrected French text only where it happened to be
looking. These tests scan the whole repository instead, so the next occurrence
fails here rather than reaching a user.

Pure Python: no Home Assistant, so unlike the rest of the suite these run
natively on any platform — on Windows with
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_i18n_hygiene.py`, since the
harness plugin itself cannot be imported there.
"""

from __future__ import annotations

import json
from pathlib import Path
import re

import pytest

REPO = Path(__file__).resolve().parent.parent
COMPONENT = REPO / "custom_components" / "dooya"

# Unambiguous French function words. Each one is either absent from English or
# vanishingly rare in it; genuinely ambiguous words ("plus", "son", "car",
# "on", "a") are deliberately left out, and two distinct markers are required
# on the same line, so a false positive needs two rare coincidences at once.
FRENCH_MARKERS = frozenset(
    ["le", "la", "les", "des", "une", "du", "pour", "dans", "est", "sont", "avec", "sans", "par", "qui", "que", "aux", "cette", "ses", "au", "ou", "si", "depuis", "vers", "entre", "tous", "toutes", "nom", "temps", "volet", "volets", "trame", "trames", "passerelle", "canal", "etape", "liste", "lister", "retourner", "initialiser", "configurer", "annuler", "programmer", "demarrer", "marquer", "recaler", "refleter", "suivre", "repercuter", "nettoyer", "decharger", "charger", "modifier", "permet", "donnees", "valeurs", "fichier", "selon", "ainsi", "donc", "mais", "encore", "deja", "aucun", "aucune", "reçue", "connecté", "événement", "envoyé", "été", "où", "déjà"]
)

# Files and trees where French is correct and expected.
ALLOWED_FRENCH = (
    "docs/",  # working notes, not shipped
    "tools/",  # generators embedding community-forum prose verbatim
    "custom_components/dooya/translations/fr.json",  # the French locale itself
    # The bundled card carries its own bilingual string tables and inline
    # `fr ? "…" : "…"` ternaries; French is part of its source by design.
    "custom_components/dooya/frontend/dooya-cover-card.js",
    "tests/test_i18n_hygiene.py",  # this file lists French words on purpose
)

SCANNED_SUFFIXES = {".py", ".json", ".yaml", ".yml", ".md", ".js"}


def _scanned_files() -> list[Path]:
    """Every repository file that must not contain French."""
    files: list[Path] = []
    for path in sorted(REPO.rglob("*")):
        if not path.is_file() or path.suffix not in SCANNED_SUFFIXES:
            continue
        rel = path.relative_to(REPO).as_posix()
        if rel.startswith(".git/") or "__pycache__" in rel or ".venv" in rel:
            continue
        if any(rel.startswith(allowed) or rel == allowed for allowed in ALLOWED_FRENCH):
            continue
        files.append(path)
    return files


def _french_lines(path: Path) -> list[tuple[int, str]]:
    """Return (line number, text) for lines carrying two or more markers."""
    hits: list[tuple[int, str]] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    for number, line in enumerate(text.splitlines(), 1):
        words = {
            word.strip(".,;:!?()[]{}\"'`«»").lower()
            for word in line.replace("'", "' ").split()
        }
        if len(words & FRENCH_MARKERS) >= 2:
            hits.append((number, line.strip()))
    return hits


def test_no_french_outside_the_french_locale() -> None:
    """No French text anywhere it would reach an English-speaking user.

    This is the guard for #26 (a hardcoded `aucun` in the config flow, shown in
    the device step) and #29 (a French log message inside the README's ESPHome
    snippet — on the HACS landing page, which is the most-read file there is).
    """
    offenders: list[str] = []
    for path in _scanned_files():
        for number, line in _french_lines(path):
            offenders.append(f"{path.relative_to(REPO).as_posix()}:{number}: {line}")

    assert not offenders, (
        "French text found outside the French locale. Translate it, or add the "
        "file to ALLOWED_FRENCH if French genuinely belongs there:\n  "
        + "\n  ".join(offenders)
    )


def _flatten(data: dict, prefix: str = "") -> dict[str, str]:
    """Flatten a nested translation file into dotted key -> value."""
    flat: dict[str, str] = {}
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(_flatten(value, path))
        else:
            flat[path] = value
    return flat


@pytest.fixture(scope="module")
def locales() -> dict[str, dict[str, str]]:
    """The three translation files, flattened to dotted keys."""
    return {
        name: _flatten(json.loads(path.read_text(encoding="utf-8")))
        for name, path in (
            ("strings", COMPONENT / "strings.json"),
            ("en", COMPONENT / "translations" / "en.json"),
            ("fr", COMPONENT / "translations" / "fr.json"),
        )
    }


def test_english_translation_never_drifts_from_strings(
    locales: dict[str, dict[str, str]],
) -> None:
    """`translations/en.json` must be identical to `strings.json`.

    The guard for #22. `strings.json` is the source the developer edits, but
    `translations/en.json` is what Home Assistant actually serves, so the two
    silently diverging means English users read older text than French ones —
    which is exactly what happened for three strings.
    """
    strings, english = locales["strings"], locales["en"]

    assert strings.keys() == english.keys(), (
        "strings.json and translations/en.json have different keys: "
        f"only in strings.json: {sorted(strings.keys() - english.keys())}; "
        f"only in en.json: {sorted(english.keys() - strings.keys())}"
    )

    drifted = {
        key: (strings[key], english[key])
        for key in strings
        if strings[key] != english[key]
    }
    assert not drifted, (
        "translations/en.json has fallen behind strings.json for these keys "
        f"(strings.json value, en.json value): {drifted}"
    )


def test_every_locale_covers_the_same_keys(
    locales: dict[str, dict[str, str]],
) -> None:
    """The French locale must cover exactly the keys English does.

    A missing key makes Home Assistant fall back to English mid-sentence; an
    extra one is dead weight that outlives the string it translated.
    """
    english, french = locales["en"], locales["fr"]

    assert english.keys() == french.keys(), (
        f"missing from fr.json: {sorted(english.keys() - french.keys())}; "
        f"stale in fr.json: {sorted(french.keys() - english.keys())}"
    )


def test_placeholders_match_across_locales(
    locales: dict[str, dict[str, str]],
) -> None:
    """Both locales must use the same `{placeholder}` set for every key.

    A placeholder present in one locale and absent in the other either drops a
    value the user needs or raises at render time, depending which way round it
    is — and it is invisible until that exact screen is shown.
    """

    def placeholders(value: str) -> set[str]:
        return set(re.findall(r"\{(\w+)\}", value))

    mismatched = {
        key: (placeholders(locales["en"][key]), placeholders(locales["fr"][key]))
        for key in locales["en"].keys() & locales["fr"].keys()
        if placeholders(locales["en"][key]) != placeholders(locales["fr"][key])
    }
    assert not mismatched, (
        f"placeholder mismatch between en.json and fr.json (en, fr): {mismatched}"
    )
