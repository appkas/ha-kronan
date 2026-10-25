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
        vol.Optional("offset", default=0): vol.All(vol.Coerce(int), vol.Range(min=0)),
    }
)
GET_SLOTS_SCHEMA = vol.Schema({_ENTRY: cv.string, vol.Optional("address_id"): vol.Coerce(int)})
RESERVE_SCHEMA = vol.Schema(
    {
        _ENTRY: cv.string,
        vol.Required("slot_id"): vol.Coerce(int),
        vol.Optional("address_id"): vol.Coerce(int),
        vol.Optional("return_bags", default=False): cv.boolean,
    }
)
ADD_TO_ORDER_SCHEMA = vol.Schema({_ENTRY: cv.string})
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


def _address(a: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": a.get("id"),
        "street": a.get("streetAddress1"),
        "postal_code": a.get("postalCode"),
        "city": a.get("city"),
        "default": bool(a.get("isDefaultShipping")),
    }


def _hhmm(value: Any) -> str | None:
    return str(value)[:5] if value else None


async def _default_address(entry: KronanConfigEntry, address_id: int | None) -> tuple[int, list[dict[str, Any]]]:
    """The address asked for, else the default shipping address, else the only one."""
    addresses = [_address(a) for a in await _read(entry, entry.runtime_data.client.get_addresses())]
    if address_id is not None:
        if not any(a["id"] == address_id for a in addresses):
            raise ServiceValidationError(f"Address {address_id} is not one of this account's addresses")
        return address_id, addresses
    chosen = next((a for a in addresses if a["default"]), addresses[0] if len(addresses) == 1 else None)
    if chosen is None:
        raise ServiceValidationError("No default delivery address; pass address_id")
    return chosen["id"], addresses


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
        limit, offset = call.data[ATTR_LIMIT], call.data["offset"]
        stats, total = await _read(
            entry,
            entry.runtime_data.client.get_purchase_stats(sort=call.data["sort"], limit=limit, offset=offset),
        )
        following = offset + len(stats)
        return {
            "products": [_favorite(s) for s in stats if not s.get("isIgnored") and (s.get("product") or {}).get("sku")],
            "total": total,
            # Where the next page starts, or None when this was the last one.
            "next_offset": following if stats and following < total else None,
        }

    async def get_delivery_slots(call: ServiceCall) -> ServiceResponse:
        entry = _entry(hass, call)
        address_id, addresses = await _default_address(entry, call.data.get("address_id"))
        days = await _read(entry, entry.runtime_data.client.get_delivery_slots(address_id))
        return {
            "address_id": address_id,
            "addresses": addresses,
            "days": [
                {
                    "date": day.get("day"),
                    "slots": [
                        {
                            "slot_id": slot.get("slotId"),
                            "start": _hhmm(slot.get("timeStart")),
                            "end": _hhmm(slot.get("timeStop")),
                            "available": slot.get("availabilityStatus"),
                        }
                        for slot in day.get("slots") or []
                    ],
                }
                for day in days
            ],
        }

    async def reserve_delivery_slot(call: ServiceCall) -> ServiceResponse:
        entry = _entry(hass, call)
        address_id, _ = await _default_address(entry, call.data.get("address_id"))
        result = await _read(
            entry,
            entry.runtime_data.client.reserve_delivery(call.data["slot_id"], address_id, call.data["return_bags"]),
        )
        await entry.runtime_data.async_request_refresh()
        return {
            "order_token": result.get("orderToken"),
            "date": result.get("deliveryDate"),
            "start": _hhmm(result.get("timeStart")),
            "end": _hhmm(result.get("timeStop")),
            "fees": result.get("fees") or {},
            "authorized_amount": result.get("authorizedAmount"),
        }

    async def add_cart_to_order(call: ServiceCall) -> ServiceResponse:
        entry = _entry(hass, call)
        result = await _read(entry, entry.runtime_data.client.add_checkout_to_order())
        await entry.runtime_data.async_request_refresh()
        return {"order_token": result.get("orderToken"), "authorized_amount": result.get("authorizedAmount")}

    hass.services.async_register(DOMAIN, "add_to_cart", add_to_cart, schema=ADD_TO_CART_SCHEMA)
    hass.services.async_register(
        DOMAIN, "get_delivery_slots", get_delivery_slots, schema=GET_SLOTS_SCHEMA, supports_response=SupportsResponse.ONLY
    )
    hass.services.async_register(
        DOMAIN, "reserve_delivery_slot", reserve_delivery_slot, schema=RESERVE_SCHEMA, supports_response=SupportsResponse.OPTIONAL
    )
    hass.services.async_register(
        DOMAIN, "add_cart_to_order", add_cart_to_order, schema=ADD_TO_ORDER_SCHEMA, supports_response=SupportsResponse.OPTIONAL
    )
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
