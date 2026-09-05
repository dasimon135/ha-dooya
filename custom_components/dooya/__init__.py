"""Dooya RF Covers integration for Home Assistant."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, Platform
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.helpers import config_validation as cv, issue_registry as ir
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, gateway_issue_id

if TYPE_CHECKING:
    from .cover import DooyaCover

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [Platform.COVER, Platform.BUTTON]


@dataclass
class DooyaRuntimeData:
    """Runtime objects shared between the platforms of a config entry."""

    cover: DooyaCover | None = None


type DooyaConfigEntry = ConfigEntry[DooyaRuntimeData]

CARD_URL = "/dooya_frontend/dooya-cover-card.js"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the bundled Lovelace card (served and auto-loaded by the frontend)."""
    try:
        await _async_register_card(hass)
    except Exception:
        # The card is a convenience on top of a working integration: failing to
        # serve it must never stop the covers from being set up.
        _LOGGER.error(
            "Could not register the bundled Dooya card; the integration still "
            "works but 'custom:dooya-cover-card' will not be available",
            exc_info=True,
        )
    return True


async def _async_register_card(hass: HomeAssistant) -> None:
    """Serve the card file, then get the browser to load it.

    `http` is a hard dependency because `hass.http` is dereferenced here;
    `frontend` is only an after_dependency. The card is a convenience, and
    environments without the `hass_frontend` package (the HA test harness, for
    one) must still be able to set the integration up.
    """
    from homeassistant.components.http import StaticPathConfig

    card_path = Path(__file__).parent / "frontend" / "dooya-cover-card.js"
    # cache_headers=False, deliberately: `?v=` below moves with the file, but a
    # resource somebody registered by hand carries a frozen URL, and 31 days of
    # `max-age` on it means no reload revalidates the card for a month.
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(card_path), False)]
    )
    # Cache-bust on a digest of the file rather than the integration version, so
    # every shipped change of the card is a URL no browser can already hold.
    digest = await hass.async_add_executor_job(_card_digest, card_path)
    url = f"{CARD_URL}?v={digest}"

    if await _async_register_resource(hass, url):
        return

    # Lovelace is not up yet, or is not there at all. Try once more when Home
    # Assistant has finished starting, and only fall back if that fails too:
    # doing both would put two copies of the card in one page, and the loser of
    # that race cannot be replaced.
    if hass.state is CoreState.running:
        _async_add_module_url(hass, url)
        return

    async def _retry(_event: Any) -> None:
        if not await _async_register_resource(hass, url):
            _async_add_module_url(hass, url)

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _retry)


async def _async_register_resource(hass: HomeAssistant, url: str) -> bool:
    """Register the card as a Lovelace resource. True when it is registered.

    This is how HACS delivers every custom card, and the difference is not
    cosmetic: Lovelace loads its own resources and WAITS for them before it
    renders a card, while nothing waits for a frontend module URL. Handed to
    the module list, this card rendered as a configuration error in the Android
    companion app on every single load -- reinstalling the app changed nothing,
    so it was never a cache -- and ha-rf-fan#44 reports the same failure from
    another user, plus about one hard reload in three in a desktop browser. As
    a dashboard resource it works every time.

    Storage mode only. In YAML mode the resource list is the user's file and
    this integration has no business writing to it, so the caller falls back.
    """
    try:
        from homeassistant.components.lovelace.const import (
            LOVELACE_DATA,
            MODE_STORAGE,
        )
        from homeassistant.components.lovelace.resources import (
            ResourceStorageCollection,
        )
    except ImportError:  # pragma: no cover - lovelace is a core component
        return False

    data = hass.data.get(LOVELACE_DATA)
    if data is None or data.resource_mode != MODE_STORAGE:
        return False

    resources = data.resources
    if not isinstance(resources, ResourceStorageCollection):
        # Storage mode without a storage collection cannot happen, but the
        # write calls below only exist on that class.
        return False
    # `async_items()` does NOT read the store, while `async_create_item()` does.
    # On a start where Lovelace has not read its resources yet, the lookup would
    # answer "empty", this would conclude nothing is registered, and the create
    # would append a second copy of what was already there -- one more per
    # restart (ha-rf-fan#44). `async_get_info()` is the public way to make sure
    # the store has been read.
    await resources.async_get_info()

    # Matched on the PATH, not the whole URL: the query changes with the file,
    # and a copy the user registered by hand carries a different one (or none).
    # Adopting that copy is what keeps a hand-registered entry from becoming a
    # second, stale card.
    ours = [
        item
        for item in resources.async_items()
        if str(item.get("url", "")).split("?")[0] == CARD_URL
    ]

    if not ours:
        await resources.async_create_item({"res_type": "module", "url": url})
        _LOGGER.debug("Registered the Dooya card as a Lovelace resource: %s", url)
        return True

    keep, *extras = ours
    if keep.get("url") != url:
        await resources.async_update_item(keep["id"], {"url": url})
        _LOGGER.debug("Updated the Dooya card resource to %s", url)
    for extra in extras:
        await resources.async_delete_item(extra["id"])
        _LOGGER.warning(
            "Removed a duplicate registration of the Dooya card (%s); two "
            "copies race to define the same element and the older one wins",
            extra.get("url"),
        )
    return True


def _async_add_module_url(hass: HomeAssistant, url: str) -> None:
    """Fall back to the frontend's extra module list.

    `after_dependencies` only ORDERS the setup when the frontend is set up at
    all; it does not guarantee it exists. Nothing waits for these URLs, which is
    why this is the fallback and not the path.
    """
    from homeassistant.components import frontend

    if "frontend" not in hass.config.components:
        _LOGGER.debug(
            "Frontend not loaded: the card stays served at %s but is not auto-loaded",
            CARD_URL,
        )
        return
    frontend.add_extra_js_url(hass, url)


def _card_digest(path: Path) -> str:
    """Short content digest of the card file, used as its cache-buster."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


async def async_setup_entry(hass: HomeAssistant, entry: DooyaConfigEntry) -> bool:
    """Set up a Dooya config entry."""
    entry.runtime_data = DooyaRuntimeData()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Reload the entry when options change so the new ESPHome device,
    # travel times and repeat count apply without an HA restart.
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: DooyaConfigEntry) -> None:
    """Reload the entry after its options changed."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: DooyaConfigEntry) -> bool:
    """Unload a Dooya config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        ir.async_delete_issue(hass, DOMAIN, gateway_issue_id(entry.entry_id))
    return unloaded
