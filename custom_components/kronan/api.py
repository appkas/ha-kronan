"""Small async client for the Krónan Snjallverslun public API."""

from __future__ import annotations

from typing import Any

import aiohttp

from .const import API_BASE_URL

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)


class KronanError(Exception):
    """Base error for the Krónan API."""


class KronanAuthError(KronanError):
    """The access token was rejected."""


class KronanPermissionError(KronanError):
    """The token works but may not use this endpoint (403)."""


class KronanConnectionError(KronanError):
    """The API could not be reached."""


class KronanRateLimitError(KronanError):
    """Too many requests (the API allows 200 per 200 seconds)."""


def normalize_token(token: str) -> str:
    """Accept the token with or without the `AccessToken ` prefix."""
    token = token.strip()
    if token.lower().startswith("accesstoken "):
        token = token.split(" ", 1)[1].strip()
    return token


class KronanApiClient:
    """Wraps the endpoints this integration uses."""

    def __init__(self, session: aiohttp.ClientSession, token: str) -> None:
        self._session = session
        self._token = normalize_token(token)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        allow_404: bool = False,
    ) -> Any:
        headers = {
            "Authorization": f"AccessToken {self._token}",
            "Accept": "application/json",
        }
        try:
            async with self._session.request(
                method,
                f"{API_BASE_URL}{path}",
                headers=headers,
                params=params,
                json=json,
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                if resp.status == 401:
                    raise KronanAuthError("Access token rejected (401)")
                if resp.status == 403:
                    raise KronanPermissionError(f"The access token may not use {path} (403)")
                if resp.status == 429:
                    raise KronanRateLimitError("Rate limited by the Krónan API")
                if resp.status == 404 and allow_404:
                    return None
                if resp.status == 204:
                    return None
                if resp.status >= 400:
                    body = await resp.text()
                    raise KronanError(f"Krónan API returned {resp.status}: {body[:200]}")
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise KronanConnectionError(str(err) or type(err).__name__) from err

    @staticmethod
    def _first(data: Any) -> dict[str, Any] | None:
        """Several endpoints return a one-item list."""
        if isinstance(data, list):
            return data[0] if data else None
        return data

    async def get_me(self) -> dict[str, Any]:
        """Identity behind the token: {"type": "user"|"customer_group", "name": ...}."""
        me = self._first(await self._request("GET", "/api/v1/me/"))
        if not me:
            raise KronanError("Empty identity response")
        return me

    async def get_active_order(self) -> dict[str, Any] | None:
        """The order currently on its way or booked, or None when there is none."""
        return await self._request("GET", "/api/v1/orders/currently-active/", allow_404=True)

    async def get_orders(self, limit: int = 10) -> list[dict[str, Any]]:
        """Most recent orders first."""
        data = await self._request("GET", "/api/v1/orders/", params={"limit": limit})
        if isinstance(data, dict):
            return data.get("results") or []
        return data or []

    async def get_checkout(self) -> dict[str, Any] | None:
        """The active checkout (the cart)."""
        return self._first(await self._request("GET", "/api/v1/checkout/"))

    async def get_order(self, token: str) -> dict[str, Any]:
        """One order with its lines (name, quantity, price, thumbnail)."""
        return await self._request("GET", f"/api/v1/orders/{token}/")

    async def get_purchase_stats(self, sort: str = "most_frequent", limit: int = 40) -> list[dict[str, Any]]:
        """Products this account buys, with how often and how many (lifetime stats)."""
        data = await self._request(
            "GET", "/api/v1/product-purchase-stats/", params={"sort": sort, "limit": limit}
        )
        if isinstance(data, dict):
            return data.get("results") or []
        return data or []

    async def replace_checkout_lines(self, lines: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Set the whole cart to `lines`. The API's `replace` defaults to true, so it is always sent."""
        return await self._request(
            "POST", "/api/v1/checkout/lines/", json={"lines": lines, "replace": True}
        )

    async def get_addresses(self) -> list[dict[str, Any]]:
        """Saved delivery addresses."""
        return await self._request("GET", "/api/v1/addresses/") or []

    async def get_delivery_slots(self, address_id: int) -> list[dict[str, Any]]:
        """Days with delivery windows and how much room each has left (0 = full, -1 = unlimited)."""
        return await self._request("POST", "/api/v1/slots/delivery/", json={"addressId": address_id}) or []

    async def reserve_delivery(self, slot_id: int, address_id: int, return_bags: bool) -> dict[str, Any]:
        """Book a delivery window. This creates an order and authorizes payment on the saved card."""
        return await self._request(
            "POST",
            "/api/v1/slots/delivery/reserve/",
            json={"slotId": slot_id, "addressId": address_id, "returnBags": return_bags},
        )

    async def add_checkout_to_order(self) -> dict[str, Any]:
        """Move the cart into the booked order. Authorizes the new total on the saved card."""
        return await self._request("POST", "/api/v1/checkout/add-to-order/")

    async def get_shopping_note(self) -> dict[str, Any] | None:
        """The shopping note (shopping list)."""
        return self._first(await self._request("GET", "/api/v1/shopping-notes/"))

    async def add_note_line(self, text: str) -> dict[str, Any] | None:
        """Add a freeform line to the shopping note."""
        return await self._request("POST", "/api/v1/shopping-notes/add-line/", json={"text": text})

    async def rename_note_line(self, token: str, text: str) -> dict[str, Any] | None:
        """Change the text of a shopping note line."""
        return await self._request(
            "PATCH", "/api/v1/shopping-notes/change-line/", json={"token": token, "text": text}
        )

    async def toggle_note_line(self, token: str) -> dict[str, Any] | None:
        """Flip a line between completed and not completed."""
        return await self._request(
            "PATCH", "/api/v1/shopping-notes/toggle-complete-on-line/", json={"token": token}
        )

    async def delete_note_line(self, token: str) -> None:
        """Remove a line from the shopping note."""
        await self._request("DELETE", "/api/v1/shopping-notes/delete-line/", params={"token": token})
