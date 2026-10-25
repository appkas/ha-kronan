"""Sensors for the next delivery and the cart."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import MAX_ATTRIBUTE_LINES
from .coordinator import KronanConfigEntry, KronanCoordinator
from .entity import KronanEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: KronanConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [
            NextDeliverySensor(coordinator),
            CartItemsSensor(coordinator),
            CartTotalSensor(coordinator),
        ]
    )


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class NextDeliverySensor(KronanEntity, SensorEntity):
    """When the next order arrives: the start of its time window."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: KronanCoordinator) -> None:
        super().__init__(coordinator, "next_delivery")

    @property
    def native_value(self) -> datetime | None:
        delivery = self.coordinator.data.next_delivery()
        if delivery is None:
            return None
        if delivery.start:
            return delivery.start
        return dt_util.start_of_local_day(delivery.day)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        delivery = data.next_delivery()
        if delivery is None:
            return {}
        attrs: dict[str, Any] = {
            "order_token": delivery.token,
            "type": delivery.type,
            "status": delivery.status,
            "status_display": delivery.status_display,
            "delivery_date": delivery.day.isoformat(),
            "window_start": _iso(delivery.start),
            "window_end": _iso(delivery.end),
            "eta": _iso(delivery.eta),
            "total": delivery.total,
            "item_count": delivery.item_count,
        }
        active = data.active_order or {}
        if str(active.get("orderToken")) == delivery.token:
            lines = active.get("lines") or []
            attrs |= {
                "changes_allowed_until": active.get("allowAdditionalOrderLinesUntil"),
                "needed_for_free_shipping": active.get("neededForFreeShipping"),
                "store": (active.get("store") or {}).get("name"),
                "lines": [
                    {"name": line.get("name"), "quantity": line.get("quantity")}
                    for line in lines[:MAX_ATTRIBUTE_LINES]
                ],
            }
        return attrs


class _CartSensor(KronanEntity, SensorEntity):
    @property
    def _checkout(self) -> dict[str, Any]:
        return self.coordinator.data.checkout or {}

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        checkout = self._checkout
        subtotal = checkout.get("subtotal") or 0
        cutoff = checkout.get("shippingFeeCutoff")
        return {
            "subtotal": subtotal,
            "total": checkout.get("total"),
            "shipping_fee": checkout.get("shippingFee"),
            "needed_for_free_shipping": max(0, cutoff - subtotal) if cutoff else None,
            "lines": [
                {
                    "name": (line.get("product") or {}).get("name"),
                    "quantity": line.get("quantity"),
                    "total": line.get("total"),
                }
                for line in (checkout.get("lines") or [])[:MAX_ATTRIBUTE_LINES]
            ],
        }


class CartItemsSensor(_CartSensor):
    """How many items are in the cart."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: KronanCoordinator) -> None:
        super().__init__(coordinator, "cart_items")

    @property
    def native_value(self) -> int:
        return sum(int(line.get("quantity") or 0) for line in self._checkout.get("lines") or [])


class CartTotalSensor(_CartSensor):
    """What the cart costs, in krónur."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "ISK"
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: KronanCoordinator) -> None:
        super().__init__(coordinator, "cart_total")

    @property
    def native_value(self) -> int | None:
        return self._checkout.get("total")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        # The line list lives on the item count sensor; keep this one small.
        return {}
