from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

from api.job_store import get_job
from api.models import JobStatus


async def vendor_progress_stream(job_id: str) -> AsyncGenerator[dict, None]:
    """
    SSE generator that streams vendor status updates until the job completes.
    Polls internal job state every 300 ms.
    """
    seen: dict[str, str] = {}

    while True:
        job = get_job(job_id)
        if not job:
            yield {"data": json.dumps({"error": "job not found"})}
            return

        # Emit new/changed vendor statuses
        with job._lock:
            progress_snapshot = dict(job.vendor_progress)
            current_status = job.status

        for vendor, status in progress_snapshot.items():
            if seen.get(vendor) != status:
                seen[vendor] = status
                yield {"data": json.dumps({"vendor": vendor, "status": status})}

        if current_status in (JobStatus.complete, JobStatus.error):
            yield {"data": json.dumps({"done": True, "status": current_status})}
            return

        await asyncio.sleep(0.3)
