"""Service tests: cart changes are sent as a whole cart, orders come back as responses."""

from __future__ import annotations

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.kronan.const import API_BASE_URL, DOMAIN

from .conftest import CHECKOUT

LINES_URL = f"{API_BASE_URL}/api/v1/checkout/lines/"


def _posted(aioclient_mock) -> dict:
    return next(c[2] for c in reversed(aioclient_mock.mock_calls) if c[0] == "POST" and str(c[1]).endswith("/checkout/lines/"))


async def test_add_to_cart_merges_with_current_cart(hass: HomeAssistant, setup_integration, aioclient_mock) -> None:
    aioclient_mock.post(LINES_URL, json=CHECKOUT[0])
    await hass.services.async_call(
        DOMAIN,
        "add_to_cart",
        {"items": [{"sku": "300", "quantity": 2}, {"sku": "500"}]},
        blocking=True,
    )
    body = _posted(aioclient_mock)
    assert body["replace"] is True
    assert body["lines"] == [
        {"sku": "300", "quantity": 5, "substitution": False},
        {"sku": "400", "quantity": 1, "substitution": True},
        {"sku": "500", "quantity": 1, "substitution": True},
    ]


async def test_add_single_sku(hass: HomeAssistant, setup_integration, aioclient_mock) -> None:
    aioclient_mock.post(LINES_URL, json=CHECKOUT[0])
    await hass.services.async_call(DOMAIN, "add_to_cart", {"sku": "400", "quantity": 3}, blocking=True)
    assert {"sku": "400", "quantity": 4, "substitution": True} in _posted(aioclient_mock)["lines"]


async def test_set_quantity_zero_removes(hass: HomeAssistant, setup_integration, aioclient_mock) -> None:
    after = {**CHECKOUT[0], "lines": CHECKOUT[0]["lines"][:1], "subtotal": 897, "total": 897}
    aioclient_mock.post(LINES_URL, json=after)
    await hass.services.async_call(DOMAIN, "set_cart_quantity", {"sku": "400", "quantity": 0}, blocking=True)
    assert _posted(aioclient_mock)["lines"] == [{"sku": "300", "quantity": 3, "substitution": False}]
    await hass.async_block_till_done()
    # The cart sensors follow the checkout the API returned, without waiting for the next poll.
    assert hass.states.get("sensor.kronan_cart_items").state == "3"


async def test_cart_lines_carry_sku_and_thumbnail(hass: HomeAssistant, setup_integration) -> None:
    line = hass.states.get("sensor.kronan_cart_items").attributes["lines"][0]
    assert line == {"sku": "300", "name": "Skyr", "quantity": 3, "price": 299, "total": 897, "thumbnail": "https://img/skyr.jpg"}


async def test_get_orders(hass: HomeAssistant, setup_integration) -> None:
    result = await hass.services.async_call(DOMAIN, "get_orders", {}, blocking=True, return_response=True)
    assert [o["date"] for o in result["orders"]] == ["2026-10-27", "2026-10-20"]
    assert result["orders"][1] == {
        "token": "22222222-2222-2222-2222-222222222222",
        "type": "delivery",
        "status": "fulfilled",
        "date": "2026-10-20",
        "total": 18500,
    }


async def test_get_order(hass: HomeAssistant, setup_integration, aioclient_mock) -> None:
    aioclient_mock.get(
        f"{API_BASE_URL}/api/v1/orders/22222222-2222-2222-2222-222222222222/",
        json={
            "token": "22222222-2222-2222-2222-222222222222",
            "status": "fulfilled",
            "type": "delivery",
            "deliveryDate": "2026-10-20",
            "total": 18500,
            "lines": [
                {"id": 9, "productName": "100 - Nýmjólk 1L", "sku": "100", "quantity": 4, "unitPrice": 219, "total": 876,
                 "thumbnail": "https://img/mjolk.jpg", "substitutionForLineId": None, "isMutable": False},
                {"id": 10, "productName": "100258326 - Þjónustugjald", "sku": "100258326", "quantity": 1, "unitPrice": 590,
                 "total": 590, "thumbnail": "", "substitutionForLineId": None, "isMutable": False},
            ],
        },
    )
    result = await hass.services.async_call(
        DOMAIN, "get_order", {"order_token": "22222222-2222-2222-2222-222222222222"}, blocking=True, return_response=True
    )
    assert result["order"]["lines"] == [
        {"sku": "100", "name": "Nýmjólk 1L", "quantity": 4, "unit_price": 219, "total": 876,
         "thumbnail": "https://img/mjolk.jpg", "substitution_for": None, "fee": False},
        {"sku": "100258326", "name": "Þjónustugjald", "quantity": 1, "unit_price": 590, "total": 590,
         "thumbnail": None, "substitution_for": None, "fee": True},
    ]


async def test_cart_error_is_raised(hass: HomeAssistant, setup_integration, aioclient_mock) -> None:
    aioclient_mock.post(LINES_URL, status=400, text='{"lines": ["Ógilt vörunúmer"]}')
    with pytest.raises(HomeAssistantError, match="400"):
        await hass.services.async_call(DOMAIN, "add_to_cart", {"sku": "999"}, blocking=True)


async def test_needs_sku_or_items(hass: HomeAssistant, setup_integration) -> None:
    with pytest.raises(Exception):
        await hass.services.async_call(DOMAIN, "add_to_cart", {"quantity": 2}, blocking=True)
