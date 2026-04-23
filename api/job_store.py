from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Optional

from api.models import CardModel, CardPriceModel, JobResponse, JobStatus


@dataclass
class JobState:
    job_id: str
    status: JobStatus = JobStatus.pending
    vendor_progress: dict = field(default_factory=dict)
    # Stored as plain dicts (CardPrice serialized via dataclasses.asdict)
    raw_vendor_results: Optional[dict] = None
    parsed_cards: Optional[list] = None
    error: Optional[str] = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def update_vendor(self, vendor: str, status: str) -> None:
        with self._lock:
            self.vendor_progress[vendor] = status

    def to_response(self) -> JobResponse:
        with self._lock:
            raw = None
            if self.raw_vendor_results is not None:
                raw = {
                    vendor: [
                        CardPriceModel(
                            card_name=p["card_name"],
                            original_query=p["original_query"],
                            price=p["price"],
                            website=p["website"],
                            found=p["found"],
                            quantity_available=p.get("quantity_available", 0),
                            set_code=p.get("set_code"),
                            collector_number=p.get("collector_number"),
                            foil=p.get("foil", False),
                        )
                        for p in prices
                    ]
                    for vendor, prices in self.raw_vendor_results.items()
                }

            parsed = None
            if self.parsed_cards is not None:
                parsed = [
                    CardModel(
                        quantity=c["quantity"],
                        name=c["name"],
                        set_code=c.get("set_code"),
                        collector_number=c.get("collector_number"),
                    )
                    for c in self.parsed_cards
                ]

            return JobResponse(
                job_id=self.job_id,
                status=self.status,
                vendor_progress=dict(self.vendor_progress),
                raw_vendor_results=raw,
                parsed_cards=parsed,
                error=self.error,
            )


_jobs: dict[str, JobState] = {}
_jobs_lock = threading.Lock()


def create_job() -> JobState:
    job_id = str(uuid.uuid4())
    job = JobState(job_id=job_id)
    with _jobs_lock:
        _jobs[job_id] = job
    return job


def get_job(job_id: str) -> Optional[JobState]:
    with _jobs_lock:
        return _jobs.get(job_id)
