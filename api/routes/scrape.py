from __future__ import annotations

import dataclasses
import math
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from api.job_store import JobState, create_job, get_job
from api.models import JobResponse, JobStatus, ScrapeRequest
from api.sse import vendor_progress_stream
from cart.cart_handler import CartHandler
from scraper_config import ScraperConfig, VendorFilterConfig, create_custom_config
from scraper_manager import ScraperManager

router = APIRouter()

# Map display names → vendor classes (same order as CartHandler.VENDORS)
VENDOR_CLASS_MAP = {
    name: type(vendor)
    for name, vendor in CartHandler.VENDORS.items()
}


@router.post("/scrape", status_code=202)
async def start_scrape(req: ScrapeRequest, request: Request) -> dict:
    job = create_job()
    loop = __import__("asyncio").get_event_loop()
    loop.run_in_executor(request.app.state.executor, _run_scrape, job.job_id, req)
    return {"job_id": job.job_id}


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job_status(job_id: str) -> JobResponse:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_response()


@router.get("/jobs/{job_id}/stream")
async def stream_job(job_id: str) -> EventSourceResponse:
    if not get_job(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    return EventSourceResponse(vendor_progress_stream(job_id))


def _run_scrape(job_id: str, req: ScrapeRequest) -> None:
    """Runs in a thread-pool thread. Must not use async/await."""
    job = get_job(job_id)
    if not job:
        return

    job.status = JobStatus.running

    try:
        vendor_classes = [
            VENDOR_CLASS_MAP[name]
            for name in req.enabled_vendors
            if name in VENDOR_CLASS_MAP
        ]

        config = ScraperConfig(
            enabled_scrapers=vendor_classes,
            vendor_filter=VendorFilterConfig(enable_filtering=False),
            headless=True,
        )
        manager = ScraperManager(config)

        parsed_cards = manager.parse_moxfield_format(req.card_list)
        job.parsed_cards = [dataclasses.asdict(c) for c in parsed_cards]

        raw_results = manager.scrape_all_parallel(
            cards=parsed_cards,
            status_callback=job.update_vendor,
        )

        # Serialize to plain dicts, replacing inf with None
        job.raw_vendor_results = {
            vendor: [_serialize_card_price(p) for p in prices]
            for vendor, prices in raw_results.items()
        }
        job.status = JobStatus.complete

    except Exception as exc:
        import traceback
        traceback.print_exc()
        job.error = str(exc)
        job.status = JobStatus.error


def _serialize_card_price(price) -> dict:
    d = dataclasses.asdict(price)
    # Replace inf/-inf with None so JSON serialization doesn't blow up
    if d.get("price") is not None and not math.isfinite(d["price"]):
        d["price"] = None
    return d
