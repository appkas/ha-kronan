"""Calendar of deliveries and pickups."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import Delivery, KronanConfigEntry, KronanCoordinator
from .entity import KronanEntity

SUMMARY = {"delivery": "Krónan: heimsending", "pickup": "Krónan: sótt í verslun"}


async def async_setup_entry(
    hass: HomeAssistant, entry: KronanConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([KronanCalendar(entry.runtime_data)])


def _event(delivery: Delivery) -> CalendarEvent:
    details = []
    if delivery.item_count:
        details.append(f"{delivery.item_count} vörur")
    if delivery.total is not None:
        details.append(f"{delivery.total:,} kr.".replace(",", "."))
    if delivery.status_display:
        details.append(delivery.status_display)
    if delivery.all_day:
        start, end = delivery.day, delivery.day + timedelta(days=1)
    else:
        start = delivery.start
        end = delivery.end if delivery.end and delivery.end > start else start + timedelta(hours=1)
    return CalendarEvent(
        start=start,
        end=end,
        summary=SUMMARY.get(delivery.type or "", "Krónan"),
        description=" · ".join(details) or None,
        uid=delivery.token,
    )


class KronanCalendar(KronanEntity, CalendarEntity):
    """Orders with a delivery or pickup date."""

    def __init__(self, coordinator: KronanCoordinator) -> None:
        super().__init__(coordinator, "deliveries")

    @property
    def event(self) -> CalendarEvent | None:
        """The current or next delivery."""
        now = dt_util.now()
        for delivery in self.coordinator.data.deliveries():
            event = _event(delivery)
            if event.end_datetime_local > now:
                return event
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        events = [_event(d) for d in self.coordinator.data.deliveries()]
        return [e for e in events if e.end_datetime_local > start_date and e.start_datetime_local < end_date]
