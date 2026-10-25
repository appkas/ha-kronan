"""The Krónan integration: orders, cart and shopping list from Krónan Snjallverslun."""

from __future__ import annotations

from homeassistant.const import CONF_ACCESS_TOKEN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import KronanApiClient
from .coordinator import KronanConfigEntry, KronanCoordinator

PLATFORMS: list[Platform] = [Platform.CALENDAR, Platform.SENSOR, Platform.TODO]


async def async_setup_entry(hass: HomeAssistant, entry: KronanConfigEntry) -> bool:
    """Set up Krónan from a config entry."""
    client = KronanApiClient(async_get_clientsession(hass), entry.data[CONF_ACCESS_TOKEN])
    coordinator = KronanCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: KronanConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
