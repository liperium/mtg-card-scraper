from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

class ParseRequest(BaseModel):
    card_list: str


class ScrapeRequest(BaseModel):
    card_list: str
    enabled_vendors: list[str]


class PinnedPrinting(BaseModel):
    set_code: str
    collector_number: str
    foil: bool


class RecalculateRequest(BaseModel):
    job_id: str
    selected_vendors: list[str]
    vendor_weights: dict[str, float] = {}
    min_cards_per_vendor: int = 1
    consolidation_budget: float = 0.0
    pinned_printings: dict[str, PinnedPrinting] = {}


class CartItemInput(BaseModel):
    card: str
    quantity: int
    price_per_unit: float
    total_price: float


class CartFormatRequest(BaseModel):
    store_name: str
    buy_list: list[CartItemInput]


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------

class VendorMeta(BaseModel):
    name: str
    shipping_cost: float
    fulfillment_label: str
    supports_bulk_add: bool
    deck_builder_url: str
    supports_set_info: bool = False
    supports_foil: bool = False


class CardModel(BaseModel):
    quantity: int
    name: str
    set_code: Optional[str] = None
    collector_number: Optional[str] = None


class CardPriceModel(BaseModel):
    card_name: str
    original_query: str
    price: Optional[float]   # None when inf (not found)
    website: str
    found: bool
    quantity_available: int = 0
    set_code: Optional[str] = None
    collector_number: Optional[str] = None
    foil: bool = False


class JobStatus(str, Enum):
    pending = "pending"
    running = "running"
    complete = "complete"
    error = "error"


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    vendor_progress: dict[str, str]
    raw_vendor_results: Optional[dict[str, list[CardPriceModel]]] = None
    parsed_cards: Optional[list[CardModel]] = None
    error: Optional[str] = None


class RecalculateResponse(BaseModel):
    best_prices: dict
    buy_lists: dict
    summary: dict
    not_found: list[str]
    warnings: list[str] = []


class CartFormatResponse(BaseModel):
    url: str
    card_list: str
    supports_bulk_add: bool
