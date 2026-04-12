from fastapi import APIRouter, HTTPException

from api.job_store import get_job
from api.models import RecalculateRequest, RecalculateResponse
from base_vendor import Card, CardPrice
from cart.cart_handler import CartHandler
from scraper_config import ScraperConfig, VendorFilterConfig
from scraper_manager import ScraperManager

router = APIRouter()


@router.post("/recalculate", response_model=RecalculateResponse)
def recalculate(req: RecalculateRequest) -> RecalculateResponse:
    job = get_job(req.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.raw_vendor_results or not job.parsed_cards:
        raise HTTPException(status_code=400, detail="Job results not available yet")

    # Reconstruct dataclass objects from stored dicts
    raw: dict[str, list[CardPrice]] = {
        vendor: [
            CardPrice(
                card_name=p["card_name"],
                original_query=p["original_query"],
                price=p["price"] if p["price"] is not None else float("inf"),
                website=p["website"],
                found=p["found"],
                quantity_available=p.get("quantity_available", 0),
            )
            for p in prices
        ]
        for vendor, prices in job.raw_vendor_results.items()
    }

    parsed_cards = [
        Card(
            quantity=c["quantity"],
            name=c["name"],
            set_code=c.get("set_code"),
            collector_number=c.get("collector_number"),
        )
        for c in job.parsed_cards
    ]

    vendor_shipping = {
        name: v.shipping_cost for name, v in CartHandler.VENDORS.items()
    }

    config = ScraperConfig(
        enabled_scrapers=[],
        vendor_filter=VendorFilterConfig(enable_filtering=False),
        headless=True,
    )
    manager = ScraperManager(config)

    results = manager.recalculate_results_for_selected_vendors(
        all_vendor_results=raw,
        parsed_cards=parsed_cards,
        selected_vendors=req.selected_vendors,
        vendor_shipping_costs=vendor_shipping,
        vendor_weights=req.vendor_weights or {},
        min_cards_per_vendor=req.min_cards_per_vendor,
        consolidation_budget=req.consolidation_budget,
    )

    # Sanitize any inf that leaked into best_prices
    for card_name, info in results.get("best_prices", {}).items():
        if info.get("best_price") is not None and not _is_finite(info["best_price"]):
            info["best_price"] = None

    return RecalculateResponse(
        best_prices=results["best_prices"],
        buy_lists=results["buy_lists"],
        summary=results["summary"],
        not_found=results["not_found"],
        warnings=results.get("warnings", []),
    )


def _is_finite(v: float) -> bool:
    import math
    return math.isfinite(v)
