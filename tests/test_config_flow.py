"""Config flow tests."""

from __future__ import annotations

import aiohttp

from homeassistant import config_entries
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.kronan.const import API_BASE_URL, DOMAIN

from .conftest import ME

ME_URL = f"{API_BASE_URL}/api/v1/me/"


async def _start(hass: HomeAssistant):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})


async def test_create_entry_strips_prefix(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(ME_URL, json=ME)
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ACCESS_TOKEN: "  AccessToken act_abc  "}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Kjartan Ásþórsson"
    assert result["data"] == {CONF_ACCESS_TOKEN: "act_abc"}
    assert aioclient_mock.mock_calls[-1][3]["Authorization"] == "AccessToken act_abc"


async def test_invalid_token(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(ME_URL, status=401)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ACCESS_TOKEN: "act_bad"})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_cannot_connect(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(ME_URL, exc=aiohttp.ClientConnectionError())
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ACCESS_TOKEN: "act_x"})
    assert result["errors"] == {"base": "cannot_connect"}


async def test_already_configured(hass: HomeAssistant, aioclient_mock, config_entry) -> None:
    config_entry.add_to_hass(hass)
    aioclient_mock.get(ME_URL, json=ME)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ACCESS_TOKEN: "act_new"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_updates_token(hass: HomeAssistant, aioclient_mock, config_entry) -> None:
    config_entry.add_to_hass(hass)
    aioclient_mock.get(ME_URL, json=ME)
    result = await config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ACCESS_TOKEN: "act_fresh"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data[CONF_ACCESS_TOKEN] == "act_fresh"


async def test_reauth_other_account(hass: HomeAssistant, aioclient_mock, config_entry) -> None:
    config_entry.add_to_hass(hass)
    aioclient_mock.get(ME_URL, json=[{"type": "user", "name": "Someone Else"}])
    result = await config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ACCESS_TOKEN: "act_other"})
    assert result["reason"] == "wrong_account"
    assert config_entry.data[CONF_ACCESS_TOKEN] == "act_test123"
