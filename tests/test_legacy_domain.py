"""Covers set up under the old `dooya` domain come over to `dooya_rf`.

The domain was renamed for the default HACS store (hacs/default#9186): `dooya` is
a core virtual integration pointing to Motion Blinds. A config entry cannot change
domain, so each old entry is copied and its registry rows re-pointed. The promise
to the user is that nothing is learned or calibrated again: same remote id and
channel, same travel times and options, same entity_id, same device.

Note what the harness gives here, and a real install after the old folder is
deleted: the loader resolves `dooya` to core's virtual integration, not to
nothing. The old entries are removed against that.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import json
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

if sys.platform == "win32":
    pytest.skip(
        "the Home Assistant test harness does not run on Windows",
        allow_module_level=True,
    )
pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant import config_entries
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dooya_rf import CARD_URL, LEGACY_CARD_URL
from custom_components.dooya_rf.const import (
    CONF_CHANNEL,
    CONF_CHECK,
    CONF_COVER_NAME,
    CONF_DOOYA_ID,
    CONF_ESPHOME_DEVICE,
    CONF_TRAVEL_TIME_DOWN,
    CONF_TRAVEL_TIME_UP,
    DOMAIN,
    LEGACY_DOMAIN,
    gateway_issue_id,
)
from custom_components.dooya_rf.legacy import (
    async_legacy_installed,
    is_legacy_package,
)

GATEWAY_SLUG = "volets-dooya-rf433"
DOOYA_ID = 0x00D1C917


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Make custom_components/ visible to the test hass instance."""
    return


@pytest.fixture(autouse=True)
def _old_package_gone():
    """By default the old folder is already deleted, as after a restart."""
    with patch(
        "custom_components.dooya_rf.legacy.async_legacy_installed",
        return_value=False,
    ):
        yield


@contextmanager
def _old_package_at(path: Path) -> Iterator[None]:
    """Look for the old package at `path`, with the real on-disk check.

    Undoes `_old_package_gone` in both places it may have been bound: config_flow
    imports the function by name, at whatever moment it is first imported.
    """
    with (
        patch(
            "custom_components.dooya_rf.legacy.legacy_package_path", return_value=path
        ),
        patch(
            "custom_components.dooya_rf.legacy.async_legacy_installed",
            async_legacy_installed,
        ),
        patch(
            "custom_components.dooya_rf.config_flow.async_legacy_installed",
            async_legacy_installed,
        ),
    ):
        yield


def _legacy_entry(
    hass: HomeAssistant, title: str = "Salon", channel: int = 5, version: int = 1
) -> MockConfigEntry:
    """An entry the old `dooya` code created, with the registry rows it left."""
    entry = MockConfigEntry(
        domain=LEGACY_DOMAIN,
        title=title,
        version=version,
        unique_id=f"{DOOYA_ID:06X}_{channel}",
        data={
            CONF_ESPHOME_DEVICE: GATEWAY_SLUG,
            CONF_DOOYA_ID: DOOYA_ID,
            CONF_CHANNEL: channel,
            CONF_CHECK: 7,
            CONF_COVER_NAME: title,
            CONF_TRAVEL_TIME_UP: 20.0,
            CONF_TRAVEL_TIME_DOWN: 18.0,
        },
        options={CONF_TRAVEL_TIME_UP: 23.5},
    )
    entry.add_to_hass(hass)
    devices = dr.async_get(hass)
    device = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(LEGACY_DOMAIN, entry.entry_id)},
        name=title,
    )
    devices.async_update_device(device.id, name_by_user=f"My {title}")
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "cover",
        LEGACY_DOMAIN,
        entry.entry_id,
        config_entry=entry,
        device_id=device.id,
        suggested_object_id=title.lower(),
    )
    registry.async_get_or_create(
        "button",
        LEGACY_DOMAIN,
        f"{entry.entry_id}_mark_open",
        config_entry=entry,
        device_id=device.id,
        suggested_object_id=f"{title.lower()}_mark_open",
    )
    return entry


async def _start(hass: HomeAssistant) -> None:
    """Set the integration up, as adding a first entry does."""
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()


async def test_an_old_entry_comes_over_with_its_settings_and_entity_ids(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    old = _legacy_entry(hass)
    [old_device] = dr.async_entries_for_config_entry(dr.async_get(hass), old.entry_id)

    await _start(hass)

    assert hass.config_entries.async_get_entry(old.entry_id) is None, (
        "old entry left behind"
    )
    [new] = hass.config_entries.async_entries(DOMAIN)
    assert new.title == "Salon"
    assert new.unique_id == old.unique_id
    assert new.data[CONF_DOOYA_ID] == DOOYA_ID
    assert new.data[CONF_CHANNEL] == 5
    assert "legacy_entry_id" not in new.data
    assert new.options == {CONF_TRAVEL_TIME_UP: 23.5}

    # Same entity_id, now owned by the new entry: automations keep working.
    registry = er.async_get(hass)
    cover = registry.async_get("cover.salon")
    assert cover is not None
    assert cover.platform == DOMAIN
    assert cover.config_entry_id == new.entry_id
    assert cover.unique_id == new.entry_id
    button = registry.async_get("button.salon_mark_open")
    assert button is not None
    assert button.unique_id == f"{new.entry_id}_mark_open"
    assert hass.states.get("cover.salon") is not None
    assert "cover.salon_2" not in hass.states.async_entity_ids("cover")

    # Same device, with the name the user gave it.
    [device] = dr.async_entries_for_config_entry(dr.async_get(hass), new.entry_id)
    assert (DOMAIN, new.entry_id) in device.identifiers
    assert device.id == old_device.id
    assert device.name_by_user == "My Salon"
    assert device.config_entry_id == new.entry_id
    # Moving a device with add/remove_config_entry_id is deprecated on 2026.9+.
    assert "async_update_device" not in caplog.text


async def test_every_old_entry_comes_over(hass: HomeAssistant) -> None:
    _legacy_entry(hass, "Salon", channel=5)
    _legacy_entry(hass, "Cuisine", channel=6)

    await _start(hass)

    assert not hass.config_entries.async_entries(LEGACY_DOMAIN)
    assert sorted(e.title for e in hass.config_entries.async_entries(DOMAIN)) == [
        "Cuisine",
        "Salon",
    ]
    assert hass.states.get("cover.salon") is not None
    assert hass.states.get("cover.cuisine") is not None


async def test_an_entry_from_a_newer_schema_is_not_misread(hass: HomeAssistant) -> None:
    old = _legacy_entry(hass, version=2)

    await _start(hass)

    assert hass.config_entries.async_get_entry(old.entry_id) is not None
    assert not hass.config_entries.async_entries(DOMAIN)


async def test_nothing_is_taken_while_the_old_version_still_runs(
    hass: HomeAssistant,
) -> None:
    """HACS leaves the old folder in place: importing then gives a cover two masters."""
    old = _legacy_entry(hass)

    with patch(
        "custom_components.dooya_rf.legacy.async_legacy_installed",
        return_value=True,
    ):
        await _start(hass)

    assert hass.config_entries.async_get_entry(old.entry_id) is not None
    assert not hass.config_entries.async_entries(DOMAIN)


async def test_old_repairs_are_cleared(hass: HomeAssistant) -> None:
    old = _legacy_entry(hass)
    ir.async_create_issue(
        hass,
        LEGACY_DOMAIN,
        gateway_issue_id(old.entry_id),
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="esphome_service_missing",
    )

    await _start(hass)

    assert (LEGACY_DOMAIN, gateway_issue_id(old.entry_id)) not in ir.async_get(
        hass
    ).issues


async def test_adding_the_integration_offers_to_bring_the_covers_over(
    hass: HomeAssistant,
) -> None:
    """The only way in on the first start: a domain with no entry is never set up."""
    _legacy_entry(hass, "Salon", channel=5)
    _legacy_entry(hass, "Cuisine", channel=6)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "import_legacy"
    assert "Salon" in result["description_placeholders"]["covers"]

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY, result
    assert not hass.config_entries.async_entries(LEGACY_DOMAIN)
    assert len(hass.config_entries.async_entries(DOMAIN)) == 2
    assert hass.states.get("cover.salon") is not None
    assert hass.states.get("cover.cuisine") is not None


@pytest.mark.parametrize(
    "state",
    [
        config_entries.ConfigEntryState.LOADED,
        config_entries.ConfigEntryState.SETUP_RETRY,
        config_entries.ConfigEntryState.SETUP_IN_PROGRESS,
    ],
)
async def test_no_import_while_the_old_code_still_runs(
    hass: HomeAssistant, state: config_entries.ConfigEntryState
) -> None:
    """Folder deleted, no restart yet: the 0.13 code still drives the cover.

    Importing then would give it two masters, so both ways in wait for the restart.
    Seen on a real 2026.11 instance before this guard: Add integration offered the
    import straight after the folder was deleted.
    """
    old = _legacy_entry(hass)
    old.mock_state(hass, state)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "restart_to_finish"

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_IMPORT},
        data={"legacy_entry_id": old.entry_id},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "restart_to_finish"
    assert not hass.config_entries.async_entries(DOMAIN)
    assert hass.config_entries.async_get_entry(old.entry_id) is not None


async def test_a_running_old_version_is_reported_and_left_on_disk(
    hass: HomeAssistant, tmp_path: Path
) -> None:
    """The user removes the old folder, never this integration (hacs/default#9186).

    Then, and only once it is gone, adding the integration brings the covers over.
    """
    old = _legacy_entry(hass)
    package = _package(tmp_path / "dooya", _OUR_OLD_MANIFEST)

    with _old_package_at(package):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "legacy_installed"
        assert result["description_placeholders"] == {
            "count": "1",
            "path": "custom_components/dooya",
        }
        assert (package / "manifest.json").is_file()
        assert (package / "__init__.py").is_file()
        assert hass.config_entries.async_get_entry(old.entry_id) is not None
        assert not hass.config_entries.async_entries(DOMAIN)

        # What the user does by hand, followed by the restart.
        for child in package.iterdir():
            child.unlink()
        package.rmdir()

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["step_id"] == "import_legacy"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY, result
    assert hass.config_entries.async_get_entry(old.entry_id) is None
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_somebody_elses_dooya_folder_does_not_block_the_import(
    hass: HomeAssistant, tmp_path: Path
) -> None:
    """Detection only: a `dooya` folder that is not ours is not reported, nor touched."""
    _legacy_entry(hass)
    package = _package(tmp_path / "dooya", _SOMEBODY_ELSES_MANIFEST)

    with _old_package_at(package):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

    assert result["step_id"] == "import_legacy"
    assert (package / "manifest.json").is_file()


async def test_without_old_covers_adding_the_integration_is_unchanged(
    hass: HomeAssistant,
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["step_id"] == "user"


async def test_the_card_resource_left_at_the_old_path_is_adopted(
    hass: HomeAssistant,
) -> None:
    """Left alone it points at a file nothing serves, reported on every dashboard."""
    assert await async_setup_component(hass, "lovelace", {})
    resources = hass.data[LOVELACE_DATA].resources
    await resources.async_create_item(
        {"res_type": "module", "url": f"{LEGACY_CARD_URL}?v=d5f9c4efdd64"}
    )

    await _start(hass)

    urls = [item["url"] for item in resources.async_items()]
    assert not [url for url in urls if url.startswith(LEGACY_CARD_URL)], urls
    assert len([url for url in urls if url.startswith(CARD_URL)]) == 1, urls


_OUR_OLD_MANIFEST = {
    "domain": "dooya",
    "documentation": "https://github.com/dasimon135/ha-dooya",
}
_SOMEBODY_ELSES_MANIFEST = {
    "domain": "dooya",
    "documentation": "https://example.com/another-dooya",
}


def _package(path: Path, manifest: dict[str, str]) -> Path:
    path.mkdir(parents=True)
    (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (path / "__init__.py").write_text("", encoding="utf-8")
    return path


def test_the_old_package_is_recognised(tmp_path: Path) -> None:
    assert is_legacy_package(_package(tmp_path / "dooya", _OUR_OLD_MANIFEST))


def test_somebody_elses_dooya_package_is_not_ours(tmp_path: Path) -> None:
    assert not is_legacy_package(_package(tmp_path / "dooya", _SOMEBODY_ELSES_MANIFEST))


def test_a_missing_folder_is_not_the_old_package(tmp_path: Path) -> None:
    assert not is_legacy_package(tmp_path / "dooya")
