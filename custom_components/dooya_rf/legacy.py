"""Carry the covers of the old `dooya` domain over to this one.

This integration used to be `dooya`, a domain core already uses for a
virtual integration that points users to Motion Blinds: a custom integration
with that domain overrides it (hacs/default#9186). A config entry cannot change
domain, so each old entry is copied into a new one and its registry rows are
re-pointed at it. What a user keeps: every remote id and channel, travel times,
options, and every entity_id, so automations and dashboards that name the covers
survive the rename. Calls to `dooya.mark_open` and the other two services do
not: those are now `dooya_rf.*`.

Two facts shape how this is triggered:

- Home Assistant only sets up a domain that has config entries. On the first
  start after the update `dooya_rf` has none, so nothing here runs on its own:
  the user adds the integration once, and the config flow offers the import.
  From then on `async_setup` brings over whatever is left.
- HACS installs a renamed integration into the NEW folder and leaves the old one
  in place, still loaded and still driving the covers. Importing then would give
  every cover two masters, so the flow first removes the old folder and asks
  for a restart.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import shutil

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)

from .const import (
    CONF_DOOYA_ID,
    CONF_ESPHOME_DEVICE,
    CONF_LEGACY_ENTRY_ID,
    DOMAIN,
    LEGACY_DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

# How the old package is told apart from anything else in that folder: by the
# documentation URL its manifest has always carried.
_LEGACY_DOCUMENTATION = "github.com/dasimon135/ha-dooya"


@callback
def legacy_entries(hass: HomeAssistant) -> list[ConfigEntry]:
    """The `dooya` entries this integration created, still waiting to come over.

    Filtered on shape, not only on domain: nothing else should ever own a
    `dooya` entry, but it costs nothing to make sure.
    """
    claimed = {
        entry.data.get(CONF_LEGACY_ENTRY_ID)
        for entry in hass.config_entries.async_entries(DOMAIN)
    }
    return [
        entry
        for entry in hass.config_entries.async_entries(LEGACY_DOMAIN)
        if CONF_DOOYA_ID in entry.data
        and CONF_ESPHOME_DEVICE in entry.data
        and entry.entry_id not in claimed
    ]


def legacy_package_path(hass: HomeAssistant) -> Path:
    """Where the old package was installed."""
    return Path(hass.config.path("custom_components", LEGACY_DOMAIN))


def is_legacy_package(path: Path) -> bool:
    """True when `path` holds this integration's old package."""
    try:
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return manifest.get("domain") == LEGACY_DOMAIN and _LEGACY_DOCUMENTATION in str(
        manifest.get("documentation", "")
    )


def remove_legacy_package(path: Path) -> bool:
    """Delete the old package. Refuses anything that is not provably ours."""
    if not is_legacy_package(path):
        return False
    shutil.rmtree(path)
    return True


async def async_legacy_installed(hass: HomeAssistant) -> bool:
    """True while the old package is on disk (and so loaded after a restart)."""
    return await hass.async_add_executor_job(
        is_legacy_package, legacy_package_path(hass)
    )


async def async_remove_legacy_installed(hass: HomeAssistant) -> bool:
    """Delete the old package from disk. True when it was ours and is gone."""
    removed = await hass.async_add_executor_job(
        remove_legacy_package, legacy_package_path(hass)
    )
    if removed:
        _LOGGER.warning(
            "Removed the previous version of Dooya RF Covers (custom_components/%s); "
            "restart Home Assistant, then add Dooya RF Covers again to bring your "
            "covers over",
            LEGACY_DOMAIN,
        )
    return removed


async def async_import_legacy_entries(hass: HomeAssistant) -> None:
    """Start an import flow for every old entry not already on its way over."""
    pending = legacy_entries(hass)
    if not pending:
        return
    if await async_legacy_installed(hass):
        _LOGGER.warning(
            "%d Dooya covers from the previous version are waiting to be brought "
            "over, but that version is still installed in custom_components/%s. "
            "Add Dooya RF Covers from Settings → Devices & services to remove it",
            len(pending),
            LEGACY_DOMAIN,
        )
        return
    for old in pending:
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_IMPORT},
                data={CONF_LEGACY_ENTRY_ID: old.entry_id},
            )
        )


@callback
def async_adopt_legacy_registry(hass: HomeAssistant, entry: ConfigEntry) -> str | None:
    """Re-point the old entry's entities and device at `entry`. Returns its id.

    Must run before the platforms are set up: an entity that is already loaded
    cannot change platform, and a new entity created first would take a fresh
    `cover.x_2` instead of inheriting `cover.x`.
    """
    old_id = entry.data.get(CONF_LEGACY_ENTRY_ID)
    if not old_id:
        return None

    entities = er.async_get(hass)
    for row in er.async_entries_for_config_entry(entities, old_id):
        if row.platform != LEGACY_DOMAIN:
            continue
        # Every unique id is the entry id, alone or with a suffix: only that part
        # changes.
        unique_id = row.unique_id
        if unique_id.startswith(old_id):
            unique_id = entry.entry_id + unique_id[len(old_id) :]
        entities.async_update_entity_platform(
            row.entity_id,
            DOMAIN,
            new_config_entry_id=entry.entry_id,
            new_unique_id=unique_id,
        )

    devices = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(devices, old_id):
        identifiers = {
            (DOMAIN, entry.entry_id)
            if identifier == (LEGACY_DOMAIN, old_id)
            else identifier
            for identifier in device.identifiers
        }
        try:
            # Home Assistant 2026.9+: a device belongs to one config entry and is
            # moved in one call; add/remove are deprecated (gone in 2027.8). Seen
            # on a real 2026.10 during the same migration in ha-rf-fan.
            devices.async_update_device(
                device.id,
                new_config_entry_id=entry.entry_id,
                new_identifiers=identifiers,
            )
        except TypeError:
            # Older: added before the old one is removed, since a device left with no
            # config entry is deleted, and with it the area and name the user gave it.
            devices.async_update_device(
                device.id,
                add_config_entry_id=entry.entry_id,
                new_identifiers=identifiers,
            )
            devices.async_update_device(device.id, remove_config_entry_id=old_id)

    # Repairs the old code raised can never be cleared by it again.
    issues = ir.async_get(hass)
    for domain, issue_id in list(issues.issues):
        if domain == LEGACY_DOMAIN and old_id in issue_id:
            ir.async_delete_issue(hass, domain, issue_id)

    data = dict(entry.data)
    data.pop(CONF_LEGACY_ENTRY_ID)
    hass.config_entries.async_update_entry(entry, data=data)
    _LOGGER.info("Brought %s over from the previous Dooya version", entry.title)
    return old_id
