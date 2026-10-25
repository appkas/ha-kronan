"""Data update coordinator for Krónan."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import KronanApiClient, KronanAuthError, KronanError, KronanPermissionError
from .const import CLOSED_ORDER_STATUSES, DOMAIN, MAX_LINE_QUANTITY, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

type KronanConfigEntry = ConfigEntry[KronanCoordinator]


@dataclass(frozen=True)
class Delivery:
    """An order with a delivery or pickup date, for the sensor and calendar."""

    token: str
    type: str | None
    status: str | None
    status_display: str | None
    day: date
    start: datetime | None
    end: datetime | None
    total: int | None
    item_count: int | None
    eta: datetime | None = None

    @property
    def all_day(self) -> bool:
        return self.start is None


@dataclass
class KronanData:
    """Everything one refresh fetches."""

    active_order: dict[str, Any] | None
    orders: list[dict[str, Any]] = field(default_factory=list)
    checkout: dict[str, Any] | None = None
    shopping_note: dict[str, Any] | None = None

    def deliveries(self) -> list[Delivery]:
        """Orders with a date, the active order's time window filled in."""
        active = self.active_order or {}
        found: dict[str, Delivery] = {}
        for order in self.orders:
            if order.get("status") in CLOSED_ORDER_STATUSES:
                continue
            delivery = _delivery_from_order(order)
            if delivery:
                found[delivery.token] = delivery
        token = active.get("orderToken")
        day = _parse_date(active.get("deliveryDate"))
        if token and day:
            start = _combine(day, active.get("timeStart"))
            end = _combine(day, active.get("timeStop"))
            known = found.get(str(token))
            lines = active.get("lines") or []
            found[str(token)] = Delivery(
                token=str(token),
                type=active.get("type") or (known.type if known else None),
                status=known.status if known else None,
                status_display=known.status_display if known else None,
                day=day,
                start=start or (known.start if known else None),
                end=end or (known.end if known else None),
                total=active.get("total", known.total if known else None),
                item_count=sum(int(line.get("quantity") or 0) for line in lines) if lines else (known.item_count if known else None),
                eta=known.eta if known else None,
            )
        return sorted(found.values(), key=lambda d: (d.day, d.start or datetime.min.replace(tzinfo=dt_util.UTC)))

    def next_delivery(self) -> Delivery | None:
        """The active order, else the next dated order that has not happened yet."""
        deliveries = self.deliveries()
        token = (self.active_order or {}).get("orderToken")
        if token:
            for delivery in deliveries:
                if delivery.token == str(token):
                    return delivery
        today = dt_util.now().date()
        upcoming = [d for d in deliveries if d.day >= today and d.status != "fulfilled"]
        return upcoming[0] if upcoming else None


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    return dt_util.parse_date(str(value)[:10])


def _combine(day: date, value: Any) -> datetime | None:
    """A local time on a day, in Home Assistant's time zone."""
    if not value:
        return None
    parsed: time | None = dt_util.parse_time(str(value))
    if parsed is None:
        return None
    return datetime.combine(day, parsed, tzinfo=dt_util.get_default_time_zone())


def _delivery_from_order(order: dict[str, Any]) -> Delivery | None:
    day = _parse_date(order.get("deliveryDate"))
    token = order.get("token")
    if not day or not token:
        return None
    info = order.get("deliveryInfo") or {}
    eta = dt_util.parse_datetime(info["eta"]) if info.get("eta") else None
    return Delivery(
        token=str(token),
        type=order.get("type") or None,
        status=order.get("status"),
        status_display=info.get("statusDisplay"),
        day=day,
        start=_combine(day, info.get("timeStart")),
        end=_combine(day, info.get("timeStop")),
        total=order.get("total"),
        item_count=None,
        eta=eta,
    )


class KronanCoordinator(DataUpdateCoordinator[KronanData]):
    """Fetches the active order, recent orders, the cart and the shopping note."""

    config_entry: KronanConfigEntry

    def __init__(self, hass: HomeAssistant, entry: KronanConfigEntry, client: KronanApiClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> KronanData:
        async def allowed(coro: Any, default: Any) -> Any:
            # A token may lack rights for one resource; show the rest instead of failing them all.
            try:
                return await coro
            except KronanPermissionError as err:
                _LOGGER.debug("Skipping a resource this token may not read: %s", err)
                return default

        try:
            active, orders, checkout, note = await asyncio.gather(
                allowed(self.client.get_active_order(), None),
                allowed(self.client.get_orders(), []),
                allowed(self.client.get_checkout(), None),
                allowed(self.client.get_shopping_note(), None),
            )
        except KronanAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except KronanError as err:
            raise UpdateFailed(str(err)) from err
        return KronanData(active_order=active, orders=orders, checkout=checkout, shopping_note=note)

    async def async_change_cart(self, changes: dict[str, int], *, absolute: bool) -> None:
        """Add to (or, with `absolute`, set) the quantity of each SKU; 0 removes it.

        The cart is fetched fresh first and sent back whole, so edits made in the
        Krónan app in the meantime are kept.
        """
        try:
            checkout = await self.client.get_checkout() or {}
            lines: dict[str, dict[str, Any]] = {}
            for line in checkout.get("lines") or []:
                sku = (line.get("product") or {}).get("sku")
                if sku:
                    lines[sku] = {
                        "sku": sku,
                        "quantity": int(line.get("quantity") or 0),
                        "substitution": bool(line.get("substitution")),
                    }
            for sku, quantity in changes.items():
                line = lines.setdefault(sku, {"sku": sku, "quantity": 0, "substitution": True})
                line["quantity"] = quantity if absolute else line["quantity"] + quantity
                line["quantity"] = max(0, min(MAX_LINE_QUANTITY, line["quantity"]))
            new_checkout = await self.client.replace_checkout_lines(
                [line for line in lines.values() if line["quantity"] > 0]
            )
        except KronanAuthError as err:
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(f"Krónan: {err}") from err
        except KronanError as err:
            raise HomeAssistantError(f"Krónan: {err}") from err
        if new_checkout and self.data is not None:
            self.async_set_updated_data(replace(self.data, checkout=new_checkout))
        else:
            await self.async_request_refresh()

    def set_shopping_note(self, note: dict[str, Any] | None) -> None:
        """Use the note a write call returned, so the list updates without a refetch."""
        if note and self.data is not None:
            self.async_set_updated_data(replace(self.data, shopping_note=note))
