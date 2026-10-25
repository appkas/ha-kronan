"""Delivery slot tests: looking up slots, booking one and adding the cart to the booked order."""

from __future__ import annotations

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.kronan.const import API_BASE_URL, DOMAIN

ADDRESSES = [
    {"id": 7, "streetAddress1": "Sumarhús 2", "city": "Selfoss", "postalCode": "800", "isDefaultShipping": False},
    {"id": 3, "streetAddress1": "Gata 1", "city": "Reykjavík", "postalCode": "112", "isDefaultShipping": True},
]
SLOTS = [
    {"day": "2026-10-27", "slots": [
        {"slotId": 501, "timeStart": "15:00:00", "timeStop": "17:00:00", "availabilityStatus": 4},
        {"slotId": 502, "timeStart": "17:00:00", "timeStop": "19:00:00", "availabilityStatus": 0},
    ]},
    {"day": "2026-10-28", "slots": [{"slotId": 601, "timeStart": "10:00:00", "timeStop": "12:00:00", "availabilityStatus": -1}]},
]


@pytest.fixture
def slot_api(aioclient_mock):
    aioclient_mock.get(f"{API_BASE_URL}/api/v1/addresses/", json=ADDRESSES)
    aioclient_mock.post(f"{API_BASE_URL}/api/v1/slots/delivery/", json=SLOTS)
    return aioclient_mock


def _body(mock, path: str) -> dict:
    return next(c[2] for c in reversed(mock.mock_calls) if c[0] == "POST" and str(c[1]).endswith(path))


async def test_get_slots_uses_default_address(hass: HomeAssistant, setup_integration, slot_api) -> None:
    result = await hass.services.async_call(DOMAIN, "get_delivery_slots", {}, blocking=True, return_response=True)
    assert _body(slot_api, "/slots/delivery/") == {"addressId": 3}
    assert result["address_id"] == 3
    assert result["addresses"][1] == {"id": 3, "street": "Gata 1", "postal_code": "112", "city": "Reykjavík", "default": True}
    assert result["days"][0] == {
        "date": "2026-10-27",
        "slots": [
            {"slot_id": 501, "start": "15:00", "end": "17:00", "available": 4},
            {"slot_id": 502, "start": "17:00", "end": "19:00", "available": 0},
        ],
    }


async def test_unknown_address_is_refused(hass: HomeAssistant, setup_integration, slot_api) -> None:
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "get_delivery_slots", {"address_id": 99}, blocking=True, return_response=True
        )


async def test_reserve_slot(hass: HomeAssistant, setup_integration, slot_api) -> None:
    slot_api.post(
        f"{API_BASE_URL}/api/v1/slots/delivery/reserve/",
        json={"orderToken": "abc", "slotId": 501, "deliveryDate": "2026-10-27", "timeStart": "15:00:00",
              "timeStop": "17:00:00", "fees": {"shipping": 1990}, "authorizedAmount": 1990},
        status=201,
    )
    result = await hass.services.async_call(
        DOMAIN, "reserve_delivery_slot", {"slot_id": 501, "return_bags": True}, blocking=True, return_response=True
    )
    assert _body(slot_api, "/slots/delivery/reserve/") == {"slotId": 501, "addressId": 3, "returnBags": True}
    assert result == {"order_token": "abc", "date": "2026-10-27", "start": "15:00", "end": "17:00",
                      "fees": {"shipping": 1990}, "authorized_amount": 1990}


async def test_add_cart_to_order(hass: HomeAssistant, setup_integration, aioclient_mock) -> None:
    aioclient_mock.post(f"{API_BASE_URL}/api/v1/checkout/add-to-order/", json={"orderToken": "abc", "authorizedAmount": 23880})
    result = await hass.services.async_call(DOMAIN, "add_cart_to_order", {}, blocking=True, return_response=True)
    assert result == {"order_token": "abc", "authorized_amount": 23880}
