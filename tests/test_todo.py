"""Shopping list tests."""

from __future__ import annotations

import pytest

from homeassistant.components.todo import DOMAIN as TODO_DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.kronan.const import API_BASE_URL

from .conftest import note

ENTITY = "todo.kronan_shopping_list"


async def _items(hass: HomeAssistant) -> list[dict]:
    result = await hass.services.async_call(
        TODO_DOMAIN, "get_items", {}, target={"entity_id": ENTITY}, blocking=True, return_response=True
    )
    return result[ENTITY]["items"]


async def test_items_follow_placement(hass: HomeAssistant, setup_integration) -> None:
    assert hass.states.get(ENTITY).state == "1"
    items = await _items(hass)
    assert [(i["summary"], i["status"]) for i in items] == [
        ("Egg 12 stk", "completed"),
        ("Kaffi", "needs_action"),
    ]
    assert items[0]["description"] == "2 stk."


async def test_add_item(hass: HomeAssistant, setup_integration, aioclient_mock) -> None:
    added = note([{"token": "a3", "text": "Mjólk", "quantity": None, "product": None, "placement": 0, "isCompleted": False}])[0]
    aioclient_mock.post(f"{API_BASE_URL}/api/v1/shopping-notes/add-line/", json=added)
    await hass.services.async_call(TODO_DOMAIN, "add_item", {"item": "Mjólk"}, target={"entity_id": ENTITY}, blocking=True)
    call = aioclient_mock.mock_calls[-1]
    assert call[0] == "POST" and call[2] == {"text": "Mjólk"}
    assert [i["summary"] for i in await _items(hass)] == ["Mjólk"]


async def test_complete_and_rename(hass: HomeAssistant, setup_integration, aioclient_mock) -> None:
    aioclient_mock.patch(f"{API_BASE_URL}/api/v1/shopping-notes/toggle-complete-on-line/", json=note()[0])
    aioclient_mock.patch(f"{API_BASE_URL}/api/v1/shopping-notes/change-line/", json=note()[0])
    await hass.services.async_call(
        TODO_DOMAIN, "update_item", {"item": "Kaffi", "status": "completed"}, target={"entity_id": ENTITY}, blocking=True
    )
    assert aioclient_mock.mock_calls[-1][2] == {"token": "a1"}
    await hass.services.async_call(
        TODO_DOMAIN, "update_item", {"item": "Kaffi", "rename": "Kaffibaunir"}, target={"entity_id": ENTITY}, blocking=True
    )
    assert aioclient_mock.mock_calls[-1][2] == {"token": "a1", "text": "Kaffibaunir"}


async def test_delete_item(hass: HomeAssistant, setup_integration, aioclient_mock) -> None:
    aioclient_mock.delete(f"{API_BASE_URL}/api/v1/shopping-notes/delete-line/?token=a1", status=204)
    await hass.services.async_call(TODO_DOMAIN, "remove_item", {"item": "Kaffi"}, target={"entity_id": ENTITY}, blocking=True)
    assert any(c[0] == "DELETE" and "token=a1" in str(c[1]) for c in aioclient_mock.mock_calls)


async def test_api_error_is_raised(hass: HomeAssistant, setup_integration, aioclient_mock) -> None:
    aioclient_mock.post(f"{API_BASE_URL}/api/v1/shopping-notes/add-line/", status=500)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(TODO_DOMAIN, "add_item", {"item": "X"}, target={"entity_id": ENTITY}, blocking=True)
