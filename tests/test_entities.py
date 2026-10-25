"""Entity tests: next delivery, cart, calendar and setup failures."""

from __future__ import annotations

from datetime import datetime

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.kronan.const import API_BASE_URL

from .conftest import ME


async def test_next_delivery(hass: HomeAssistant, setup_integration) -> None:
    state = hass.states.get("sensor.kronan_next_delivery")
    assert state is not None
    assert dt_util.parse_datetime(state.state) == datetime(2026, 10, 27, 15, 0, tzinfo=dt_util.UTC)
    attrs = state.attributes
    assert attrs["window_end"].startswith("2026-10-27T17:00")
    assert attrs["status_display"] == "Í vinnslu"
    assert attrs["item_count"] == 3
    assert attrs["store"] == "Krónan Granda"
    assert attrs["lines"][0] == {"name": "Nýmjólk 1L", "quantity": 2}
    assert attrs["needed_for_free_shipping"] == 14213


async def test_cart(hass: HomeAssistant, setup_integration) -> None:
    items = hass.states.get("sensor.kronan_cart_items")
    total = hass.states.get("sensor.kronan_cart_total")
    assert items.state == "4"
    assert items.attributes["needed_for_free_shipping"] == 13504
    assert [line["name"] for line in items.attributes["lines"]] == ["Skyr", "Brauð"]
    assert float(total.state) == 1496
    assert total.attributes["unit_of_measurement"] == "ISK"


async def test_calendar(hass: HomeAssistant, setup_integration, hass_client) -> None:
    state = hass.states.get("calendar.kronan_deliveries")
    assert state.attributes["message"] == "Krónan: heimsending"
    assert state.attributes["start_time"] == "2026-10-27 15:00:00"
    assert state.attributes["end_time"] == "2026-10-27 17:00:00"

    client = await hass_client()
    resp = await client.get(
        "/api/calendars/calendar.kronan_deliveries?start=2026-10-01T00:00:00Z&end=2026-11-01T00:00:00Z"
    )
    events = await resp.json()
    # The fulfilled order on the 20th has no time window, so it is an all-day event.
    assert [(e["summary"], e["start"]) for e in events] == [
        ("Krónan: heimsending", {"date": "2026-10-20"}),
        ("Krónan: heimsending", {"dateTime": "2026-10-27T15:00:00+00:00"}),
    ]


async def test_no_active_order(hass: HomeAssistant, aioclient_mock, config_entry, freezer) -> None:
    await hass.config.async_set_time_zone("Atlantic/Reykjavik")
    freezer.move_to("2026-10-26T12:00:00+00:00")
    aioclient_mock.get(f"{API_BASE_URL}/api/v1/me/", json=ME)
    aioclient_mock.get(f"{API_BASE_URL}/api/v1/orders/currently-active/", status=404)
    aioclient_mock.get(f"{API_BASE_URL}/api/v1/orders/", json={"count": 0, "results": []})
    aioclient_mock.get(f"{API_BASE_URL}/api/v1/checkout/", json=[{"token": "c", "lines": [], "subtotal": 0, "total": 199, "baggingFee": 199, "shippingFee": 0, "shippingFeeCutoff": 19900}])
    aioclient_mock.get(f"{API_BASE_URL}/api/v1/shopping-notes/", json=[{"token": "n", "name": "", "lines": []}])
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.kronan_next_delivery").state == "unknown"
    assert hass.states.get("sensor.kronan_cart_items").state == "0"
    # The bagging fee alone does not count as a cart total.
    assert float(hass.states.get("sensor.kronan_cart_total").state) == 0
    assert hass.states.get("calendar.kronan_deliveries").state == "off"
    assert hass.states.get("todo.kronan_shopping_list").state == "0"


async def test_auth_failure_starts_reauth(hass: HomeAssistant, aioclient_mock, config_entry) -> None:
    for path in ("orders/currently-active/", "orders/", "checkout/", "shopping-notes/"):
        aioclient_mock.get(f"{API_BASE_URL}/api/v1/{path}", status=401)
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == "reauth" for f in flows)


async def test_unload(hass: HomeAssistant, setup_integration) -> None:
    assert await hass.config_entries.async_unload(setup_integration.entry_id)
    assert setup_integration.state is ConfigEntryState.NOT_LOADED


async def test_entity_ids(hass: HomeAssistant, setup_integration) -> None:
    ids = sorted(s.entity_id for s in hass.states.async_all() if "kronan" in s.entity_id)
    assert ids == [
        "calendar.kronan_deliveries",
        "sensor.kronan_cart_items",
        "sensor.kronan_cart_total",
        "sensor.kronan_next_delivery",
        "todo.kronan_shopping_list",
    ]


async def test_one_forbidden_resource_keeps_the_rest(hass: HomeAssistant, aioclient_mock, config_entry, freezer) -> None:
    await hass.config.async_set_time_zone("Atlantic/Reykjavik")
    freezer.move_to("2026-10-26T12:00:00+00:00")
    from .conftest import ACTIVE_ORDER, CHECKOUT, ORDERS

    aioclient_mock.get(f"{API_BASE_URL}/api/v1/orders/currently-active/", json=ACTIVE_ORDER)
    aioclient_mock.get(f"{API_BASE_URL}/api/v1/orders/", json=ORDERS)
    aioclient_mock.get(f"{API_BASE_URL}/api/v1/checkout/", json=CHECKOUT)
    aioclient_mock.get(f"{API_BASE_URL}/api/v1/shopping-notes/", status=403)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.kronan_cart_items").state == "4"
    assert hass.states.get("todo.kronan_shopping_list").state == "0"
