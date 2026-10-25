"""The Krónan shopping note as a to-do list."""

from __future__ import annotations

from typing import Any

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import KronanError
from .coordinator import KronanConfigEntry, KronanCoordinator
from .entity import KronanEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: KronanConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([KronanShoppingList(entry.runtime_data)])


def _summary(line: dict[str, Any]) -> str:
    return line.get("text") or (line.get("product") or {}).get("name") or ""


class KronanShoppingList(KronanEntity, TodoListEntity):
    """Lines in the shopping note; ticking one off ticks it off in the Krónan app too."""

    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
    )

    def __init__(self, coordinator: KronanCoordinator) -> None:
        super().__init__(coordinator, "shopping_list")

    @property
    def _lines(self) -> list[dict[str, Any]]:
        note = self.coordinator.data.shopping_note or {}
        return sorted(note.get("lines") or [], key=lambda line: line.get("placement") or 0)

    @property
    def todo_items(self) -> list[TodoItem]:
        items = []
        for line in self._lines:
            quantity = line.get("quantity")
            items.append(
                TodoItem(
                    uid=str(line["token"]),
                    summary=_summary(line),
                    status=TodoItemStatus.COMPLETED if line.get("isCompleted") else TodoItemStatus.NEEDS_ACTION,
                    description=f"{quantity} stk." if quantity else None,
                )
            )
        return items

    async def _call(self, coro: Any) -> Any:
        try:
            return await coro
        except KronanError as err:
            raise HomeAssistantError(f"Krónan: {err}") from err

    async def async_create_todo_item(self, item: TodoItem) -> None:
        note = await self._call(self.coordinator.client.add_note_line(item.summary or ""))
        self.coordinator.set_shopping_note(note)

    async def async_update_todo_item(self, item: TodoItem) -> None:
        current = next((line for line in self._lines if str(line["token"]) == item.uid), None)
        if current is None:
            raise HomeAssistantError(f"Krónan: line {item.uid} not found")
        note = None
        if item.summary is not None and item.summary != _summary(current):
            note = await self._call(self.coordinator.client.rename_note_line(item.uid, item.summary))
        done = item.status == TodoItemStatus.COMPLETED
        if item.status is not None and done != bool(current.get("isCompleted")):
            note = await self._call(self.coordinator.client.toggle_note_line(item.uid))
        if note:
            self.coordinator.set_shopping_note(note)

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        for uid in uids:
            await self._call(self.coordinator.client.delete_note_line(uid))
        await self.coordinator.async_request_refresh()
