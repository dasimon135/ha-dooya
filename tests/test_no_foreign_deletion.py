"""The integration never deletes files, least of all outside its own folder.

It used to delete `custom_components/dooya` (its own previous version) from the
config flow, behind a manifest check and a confirmation. The HACS review asked
for that to go (hacs/default#9186): that folder belongs to whatever installed it,
and a mistake there removes code the user still depends on. The removal is now
left to the user; this scan keeps any file deletion from coming back.

Pure Python, like test_i18n_hygiene.py: runs on Windows with
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_no_foreign_deletion.py`.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

COMPONENT = Path(__file__).resolve().parent.parent / "custom_components" / "dooya_rf"
SOURCES = sorted(COMPONENT.rglob("*.py"))

# Whatever the receiver: Path.unlink/rmdir, os.unlink/rmdir/removedirs, shutil.rmtree.
_DELETING_ATTRIBUTES = frozenset({"rmtree", "unlink", "rmdir", "removedirs"})
_DELETING_MODULES = frozenset({"shutil", "send2trash"})


def _deletions(path: Path) -> list[str]:
    """Every import of a deleting module and every deleting call, with its line."""
    found: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        elif isinstance(node, ast.Attribute):
            receiver = node.value.id if isinstance(node.value, ast.Name) else ""
            if node.attr in _DELETING_ATTRIBUTES or (receiver, node.attr) == (
                "os",
                "remove",
            ):
                found.append(f"line {node.lineno}: .{node.attr}")
            continue
        else:
            continue
        found += [
            f"line {node.lineno}: import {name}"
            for name in names
            if name.split(".")[0] in _DELETING_MODULES
        ]
    return found


def test_the_scan_sees_the_sources() -> None:
    assert COMPONENT / "legacy.py" in SOURCES


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_no_file_is_ever_deleted(path: Path) -> None:
    assert not _deletions(path), f"{path.name} deletes files: {_deletions(path)}"
