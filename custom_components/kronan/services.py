"""Services: change the cart, and look up past orders to reorder from."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
import homeassistant.helpers.config_validation as cv

from .api import KronanAuthError, KronanError
from .const import DOMAIN, MAX_LINE_QUANTITY
from .coordinator import KronanConfigEntry

ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_ITEMS = "items"
ATTR_SKU = "sku"
ATTR_QUANTITY = "quantity"
ATTR_ORDER_TOKEN = "order_token"
ATTR_LIMIT = "limit"

_ENTRY = vol.Optional(ATTR_CONFIG_ENTRY_ID)
_QUANTITY = vol.All(vol.Coerce(int), vol.Range(min=0, max=MAX_LINE_QUANTITY))

ADD_TO_CART_SCHEMA = vol.All(
    vol.Schema(
        {
            _ENTRY: cv.string,
            vol.Optional(ATTR_SKU): cv.string,
            vol.Optional(ATTR_QUANTITY, default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_LINE_QUANTITY)),
            vol.Optional(ATTR_ITEMS): [
                vol.Schema(
                    {
                        vol.Required(ATTR_SKU): cv.string,
                        vol.Optional(ATTR_QUANTITY, default=1): vol.All(
                            vol.Coerce(int), vol.Range(min=1, max=MAX_LINE_QUANTITY)
                        ),
                    },
                    extra=vol.REMOVE_EXTRA,
                )
            ],
        }
    ),
    cv.has_at_least_one_key(ATTR_SKU, ATTR_ITEMS),
)
SET_QUANTITY_SCHEMA = vol.Schema({_ENTRY: cv.string, vol.Required(ATTR_SKU): cv.string, vol.Required(ATTR_QUANTITY): _QUANTITY})
GET_ORDERS_SCHEMA = vol.Schema({_ENTRY: cv.string, vol.Optional(ATTR_LIMIT, default=10): vol.All(vol.Coerce(int), vol.Range(min=1, max=50))})
PURCHASE_SORTS = ["most_frequent", "most_quantity", "recent"]
GET_FAVORITES_SCHEMA = vol.Schema(
    {
        _ENTRY: cv.string,
        vol.Optional("sort", default="most_frequent"): vol.In(PURCHASE_SORTS),
        vol.Optional(ATTR_LIMIT, default=40): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
    }
)
GET_ORDER_SCHEMA = vol.Schema({_ENTRY: cv.string, vol.Required(ATTR_ORDER_TOKEN): cv.string})


def _entry(hass: HomeAssistant, call: ServiceCall) -> KronanConfigEntry:
    """The entry named in the call, or the only loaded one."""
    loaded = [e for e in hass.config_entries.async_entries(DOMAIN) if e.state is ConfigEntryState.LOADED]
    wanted = call.data.get(ATTR_CONFIG_ENTRY_ID)
    if wanted:
        loaded = [e for e in loaded if e.entry_id == wanted]
    if not loaded:
        raise ServiceValidationError("No loaded Krónan account" + (f" with id {wanted}" if wanted else ""))
    if len(loaded) > 1:
        raise ServiceValidationError("Several Krónan accounts are set up; pass config_entry_id")
    return loaded[0]


async def _read(entry: KronanConfigEntry, coro: Any) -> Any:
    try:
        return await coro
    except KronanAuthError as err:
        entry.async_start_reauth(entry.runtime_data.hass)
        raise HomeAssistantError(f"Krónan: {err}") from err
    except KronanError as err:
        raise HomeAssistantError(f"Krónan: {err}") from err


# Order lines are named "100217418 - Hansaplast plástrar"; the SKU is already a field.
_SKU_PREFIX = re.compile(r"^\s*\d+\s*-\s*")
# Service, bag and delivery fees are order lines too, but nothing to reorder.
_FEE = re.compile(r"gjald\s*$", re.IGNORECASE)


def _order_line(line: dict[str, Any]) -> dict[str, Any]:
    name = _SKU_PREFIX.sub("", line.get("productName") or "")
    return {
        "sku": line.get("sku"),
        "name": name,
        "quantity": line.get("quantity"),
        "unit_price": line.get("unitPrice"),
        "total": line.get("total"),
        "thumbnail": line.get("thumbnail") or None,
        "substitution_for": line.get("substitutionForLineId"),
        "fee": bool(_FEE.search(name)) and not line.get("thumbnail"),
    }


def _favorite(stat: dict[str, Any]) -> dict[str, Any]:
    product = stat.get("product") or {}
    return {
        "sku": product.get("sku"),
        "name": product.get("name"),
        "thumbnail": product.get("thumbnail") or None,
        "price": product.get("discountedPrice") or product.get("price"),
        "on_sale": bool(product.get("onSale")),
        "shortage": bool(product.get("temporaryShortage")),
        "purchase_count": stat.get("purchaseCount"),
        "average_quantity": stat.get("averagePurchaseQuantity"),
        "last_quantity": stat.get("lastPurchaseQuantity"),
        "last_purchase": stat.get("lastPurchaseDate"),
        "interval_days": stat.get("averagePurchaseIntervalDays"),
    }


def _order_summary(order: dict[str, Any]) -> dict[str, Any]:
    return {
        "token": order.get("token"),
        "type": order.get("type") or None,
        "status": order.get("status"),
        "date": order.get("deliveryDate") or order.get("displayDate") or order.get("created"),
        "total": order.get("total"),
    }


def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration's services (once, for all entries)."""

    async def add_to_cart(call: ServiceCall) -> None:
        changes: dict[str, int] = {}
        for item in call.data.get(ATTR_ITEMS) or [{ATTR_SKU: call.data[ATTR_SKU], ATTR_QUANTITY: call.data[ATTR_QUANTITY]}]:
            changes[item[ATTR_SKU]] = changes.get(item[ATTR_SKU], 0) + item[ATTR_QUANTITY]
        await _entry(hass, call).runtime_data.async_change_cart(changes, absolute=False)

    async def set_cart_quantity(call: ServiceCall) -> None:
        await _entry(hass, call).runtime_data.async_change_cart(
            {call.data[ATTR_SKU]: call.data[ATTR_QUANTITY]}, absolute=True
        )

    async def get_orders(call: ServiceCall) -> ServiceResponse:
        entry = _entry(hass, call)
        orders = await _read(entry, entry.runtime_data.client.get_orders(limit=call.data[ATTR_LIMIT]))
        return {"orders": [_order_summary(o) for o in orders if o.get("status") not in ("canceled", "draft")]}

    async def get_order(call: ServiceCall) -> ServiceResponse:
        entry = _entry(hass, call)
        order = await _read(entry, entry.runtime_data.client.get_order(call.data[ATTR_ORDER_TOKEN]))
        lines = [_order_line(line) for line in order.get("lines") or []]
        return {"order": _order_summary(order) | {"lines": lines}}

    async def get_favorites(call: ServiceCall) -> ServiceResponse:
        entry = _entry(hass, call)
        stats = await _read(
            entry, entry.runtime_data.client.get_purchase_stats(sort=call.data["sort"], limit=call.data[ATTR_LIMIT])
        )
        return {"products": [_favorite(s) for s in stats if not s.get("isIgnored") and (s.get("product") or {}).get("sku")]}

    hass.services.async_register(DOMAIN, "add_to_cart", add_to_cart, schema=ADD_TO_CART_SCHEMA)
    hass.services.async_register(
        DOMAIN, "get_favorites", get_favorites, schema=GET_FAVORITES_SCHEMA, supports_response=SupportsResponse.ONLY
    )
    hass.services.async_register(DOMAIN, "set_cart_quantity", set_cart_quantity, schema=SET_QUANTITY_SCHEMA)
    hass.services.async_register(
        DOMAIN, "get_orders", get_orders, schema=GET_ORDERS_SCHEMA, supports_response=SupportsResponse.ONLY
    )
    hass.services.async_register(
        DOMAIN, "get_order", get_order, schema=GET_ORDER_SCHEMA, supports_response=SupportsResponse.ONLY
    )
