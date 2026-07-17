"""Pure helpers to match devices in the Home Assistant registries."""

from __future__ import annotations

from collections.abc import Iterable


def is_esphome_device(identifiers: Iterable[tuple[str, ...]]) -> bool:
    """Return True if any identifier belongs to the esphome domain.

    Registry identifiers are documented as (domain, id) 2-tuples, but some
    integrations store 1- or 3-element tuples; index instead of unpacking so
    a foreign device can never break Dooya entity setup.
    """
    return any(ident and ident[0] == "esphome" for ident in identifiers)
