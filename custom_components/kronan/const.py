"""Constants for the Krónan integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "kronan"

API_BASE_URL: Final = "https://api.kronan.is"
TOKEN_PREFIX: Final = "act_"

# The API allows 200 requests per 200 seconds; one refresh makes four.
UPDATE_INTERVAL: Final = timedelta(minutes=5)

# Orders in these states are not shown as upcoming deliveries.
CLOSED_ORDER_STATUSES: Final = frozenset({"canceled", "cloned", "draft"})

# Keep entity attributes well under Home Assistant's recorder limit.
MAX_ATTRIBUTE_LINES: Final = 50

# The checkout accepts at most 500 of one product.
MAX_LINE_QUANTITY: Final = 500
