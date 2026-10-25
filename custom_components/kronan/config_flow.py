"""Config flow for Krónan."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .api import (
    KronanApiClient,
    KronanAuthError,
    KronanConnectionError,
    KronanError,
    KronanPermissionError,
    normalize_token,
)
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

TOKEN_SCHEMA = vol.Schema(
    {vol.Required(CONF_ACCESS_TOKEN): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))}
)


class KronanConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ask for an access token and check it against /me."""

    VERSION = 1

    async def _validate(self, token: str) -> tuple[dict[str, Any] | None, dict[str, str]]:
        client = KronanApiClient(async_get_clientsession(self.hass), token)
        try:
            return await client.get_me(), {}
        except (KronanAuthError, KronanPermissionError):
            return None, {"base": "invalid_auth"}
        except KronanConnectionError:
            return None, {"base": "cannot_connect"}
        except KronanError:
            _LOGGER.exception("Unexpected response from the Krónan API")
            return None, {"base": "unknown"}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            token = normalize_token(user_input[CONF_ACCESS_TOKEN])
            me, errors = await self._validate(token)
            if me:
                await self.async_set_unique_id(_unique_id(me))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=me.get("name") or "Krónan", data={CONF_ACCESS_TOKEN: token}
                )
        return self.async_show_form(step_id="user", data_schema=TOKEN_SCHEMA, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            token = normalize_token(user_input[CONF_ACCESS_TOKEN])
            me, errors = await self._validate(token)
            if me:
                await self.async_set_unique_id(_unique_id(me))
                self._abort_if_unique_id_mismatch(reason="wrong_account")
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(), data_updates={CONF_ACCESS_TOKEN: token}
                )
        return self.async_show_form(step_id="reauth_confirm", data_schema=TOKEN_SCHEMA, errors=errors)


def _unique_id(me: dict[str, Any]) -> str:
    """The same account keeps the same entry when its token is replaced."""
    return f"{me.get('type', 'user')}:{me.get('name', '')}".lower()
