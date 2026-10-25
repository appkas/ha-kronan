"""Shared fixtures: a fake Krónan API with one booked delivery, a cart and a shopping note."""

from __future__ import annotations

from typing import Any

import pytest

from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.kronan.const import API_BASE_URL, DOMAIN

TOKEN = "act_test123"

ME = [{"type": "user", "name": "Kjartan Ásþórsson"}]

ACTIVE_ORDER = {
    "orderToken": "11111111-1111-1111-1111-111111111111",
    "type": "delivery",
    "deliveryDate": "2026-10-27",
    "timeStart": "15:00:00",
    "timeStop": "17:00:00",
    "address": {"id": 1, "streetAddress1": "Gata 1", "city": "Reykjavík", "postalCode": "112"},
    "store": {"id": 7, "name": "Krónan Granda"},
    "lines": [
        {"sku": "100", "name": "Nýmjólk 1L", "quantity": 2, "unitPrice": 219},
        {"sku": "200", "name": "Bananar", "quantity": 1, "unitPrice": 349},
    ],
    "subtotal": 787,
    "total": 2387,
    "freeShippingCutoff": 15000,
    "neededForFreeShipping": 14213,
    "allowAdditionalOrderLinesUntil": "2026-10-27T10:00:00Z",
}

ORDERS = {
    "count": 2,
    "next": None,
    "previous": None,
    "results": [
        {
            "token": "11111111-1111-1111-1111-111111111111",
            "created": "2026-10-25T20:00:00Z",
            "status": "unfulfilled",
            "type": "delivery",
            "total": 2387,
            "discount": 0,
            "deliveryDate": "2026-10-27",
            "allowAlterOrderLines": True,
            "deliveryInfo": {
                "timeStart": "15:00:00",
                "timeStop": "17:00:00",
                "status": 1,
                "statusDisplay": "Í vinnslu",
                "eta": None,
                "address": None,
            },
        },
        {
            "token": "22222222-2222-2222-2222-222222222222",
            "created": "2026-10-19T20:00:00Z",
            "status": "fulfilled",
            "type": "delivery",
            "total": 18500,
            "discount": 0,
            "deliveryDate": "2026-10-20",
            "allowAlterOrderLines": False,
            "deliveryInfo": None,
        },
    ],
}

CHECKOUT = [
    {
        "token": "33333333-3333-3333-3333-333333333333",
        "lines": [
            {"id": 1, "quantity": 3, "product": {"sku": "300", "name": "Skyr"}, "total": 897, "price": 299},
            {"id": 2, "quantity": 1, "product": {"sku": "400", "name": "Brauð"}, "total": 599, "price": 599},
        ],
        "subtotal": 1496,
        "total": 1496,
        "baggingFee": 0,
        "serviceFee": 0,
        "shippingFee": 1990,
        "shippingFeeCutoff": 15000,
    }
]


def note(lines: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    return [
        {
            "token": "44444444-4444-4444-4444-444444444444",
            "name": "Innkaupalisti",
            "lines": lines
            if lines is not None
            else [
                {"token": "a1", "text": "Kaffi", "quantity": None, "product": None, "placement": 1, "isCompleted": False},
                {
                    "token": "a2",
                    "text": None,
                    "quantity": 2,
                    "product": {"sku": "500", "name": "Egg 12 stk", "thumbnail": ""},
                    "placement": 0,
                    "isCompleted": True,
                },
            ],
        }
    ]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load custom_components/ in every test."""
    return


@pytest.fixture
def mock_api(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    aioclient_mock.get(f"{API_BASE_URL}/api/v1/me/", json=ME)
    aioclient_mock.get(f"{API_BASE_URL}/api/v1/orders/currently-active/", json=ACTIVE_ORDER)
    aioclient_mock.get(f"{API_BASE_URL}/api/v1/orders/", json=ORDERS)
    aioclient_mock.get(f"{API_BASE_URL}/api/v1/checkout/", json=CHECKOUT)
    aioclient_mock.get(f"{API_BASE_URL}/api/v1/shopping-notes/", json=note())
    return aioclient_mock


@pytest.fixture
def config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Kjartan Ásþórsson",
        unique_id="user:kjartan ásþórsson",
        data={CONF_ACCESS_TOKEN: TOKEN},
    )


@pytest.fixture
async def setup_integration(hass: HomeAssistant, mock_api, config_entry: MockConfigEntry, freezer) -> MockConfigEntry:
    await hass.config.async_set_time_zone("Atlantic/Reykjavik")
    freezer.move_to("2026-10-26T12:00:00+00:00")
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
