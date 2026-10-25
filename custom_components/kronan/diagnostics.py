"""Diagnostics for Krónan, with the token and address removed."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant

from .coordinator import KronanConfigEntry

TO_REDACT = {CONF_ACCESS_TOKEN, "address", "streetAddress1", "streetAddress2", "postalCode", "city"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: KronanConfigEntry) -> dict[str, Any]:
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "data": async_redact_data(asdict(coordinator.data), TO_REDACT) if coordinator.data else None,
        "deliveries": [str(d) for d in coordinator.data.deliveries()] if coordinator.data else [],
    }
