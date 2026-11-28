"""Helpers for the remote identities of one Dooya shutter."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import re
from typing import TYPE_CHECKING, Any

from .const import (
    CONF_ADDITIONAL_REMOTES,
    CONF_CHANNEL,
    CONF_DOOYA_ID,
    MAX_CHANNEL,
    entry_value,
)
from .dooya_protocol import MAX_DOOYA_ID

if TYPE_CHECKING:
    from . import DooyaConfigEntry


@dataclass(frozen=True)
class DooyaRemote:
    id: int
    channel: int


class RemoteListError(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def parse_remote_text(raw: Any) -> list[DooyaRemote]:
    if raw is None:
        return []
    if not isinstance(raw, str):
        raise RemoteListError("invalid_additional_remotes")
    remotes: list[DooyaRemote] = []
    for part in re.split(r"[,\n]", raw):
        token = part.strip()
        if not token:
            continue
        fields = token.split(":")
        if len(fields) != 2:
            raise RemoteListError("invalid_additional_remotes")
        try:
            remote_id = _parse_id(fields[0])
            channel = int(fields[1].strip())
        except ValueError as err:
            raise RemoteListError("invalid_additional_remotes") from err
        if not 0 <= channel <= MAX_CHANNEL:
            raise RemoteListError("invalid_additional_remotes")
        remote = DooyaRemote(remote_id, channel)
        if remote in remotes:
            raise RemoteListError("duplicate_remote")
        remotes.append(remote)
    return remotes


def format_remote_list(remotes: list[DooyaRemote] | tuple[DooyaRemote, ...]) -> str:
    return ", ".join(f"{remote.id:06X}:{remote.channel}" for remote in remotes)


def entry_remotes(entry: DooyaConfigEntry) -> tuple[DooyaRemote, ...]:
    primary = DooyaRemote(
        int(entry.data[CONF_DOOYA_ID]), int(entry.data[CONF_CHANNEL])
    )
    remotes = [primary]
    raw = entry_value(entry, CONF_ADDITIONAL_REMOTES, [])
    if isinstance(raw, str):
        try:
            additional = parse_remote_text(raw)
        except RemoteListError:
            additional = []
    elif isinstance(raw, (list, tuple)):
        additional = []
        for item in raw:
            remote = _remote_from_mapping(item)
            if remote is not None:
                additional.append(remote)
    else:
        additional = []
    for remote in additional:
        if remote not in remotes:
            remotes.append(remote)
    return tuple(remotes)


def entry_remote_pairs(entry: DooyaConfigEntry) -> set[tuple[int, int]]:
    return {(remote.id, remote.channel) for remote in entry_remotes(entry)}


def conflicting_entry_for_remotes(
    entries: Iterable[DooyaConfigEntry],
    remotes: Iterable[DooyaRemote],
    *,
    ignore_entry_id: str | None = None,
) -> DooyaConfigEntry | None:
    pairs = {(remote.id, remote.channel) for remote in remotes}
    for entry in entries:
        if entry.entry_id == ignore_entry_id:
            continue
        if pairs & entry_remote_pairs(entry):
            return entry
    return None


def _remote_from_mapping(value: Any) -> DooyaRemote | None:
    if not isinstance(value, Mapping):
        return None
    try:
        remote_id = int(value[CONF_DOOYA_ID])
        channel = int(value[CONF_CHANNEL])
    except (KeyError, TypeError, ValueError):
        return None
    if not 0 <= remote_id <= MAX_DOOYA_ID or not 0 <= channel <= MAX_CHANNEL:
        return None
    return DooyaRemote(remote_id, channel)


def _parse_id(raw: str) -> int:
    text = raw.strip().removeprefix("0x").removeprefix("0X")
    if not text:
        raise ValueError("empty id")
    value = int(text, 16)
    if not 0 <= value <= MAX_DOOYA_ID:
        raise ValueError("id out of range")
    return value
