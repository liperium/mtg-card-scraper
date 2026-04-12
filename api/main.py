from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Ensure project root is on the path so scraper modules resolve correctly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.routes import cart, parse, recalculate, scrape, vendors


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.executor = ThreadPoolExecutor(max_workers=4)
    yield
    app.state.executor.shutdown(wait=False)


app = FastAPI(title="MTG Card Scraper API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # Vite dev server
        "http://localhost:4173",   # Vite preview
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(vendors.router, prefix="/api")
app.include_router(parse.router, prefix="/api")
app.include_router(scrape.router, prefix="/api")
app.include_router(recalculate.router, prefix="/api")
app.include_router(cart.router, prefix="/api")

# Serve frontend static build in production (set MTG_FRONTEND_DIST env var)
_frontend_dist = os.environ.get("MTG_FRONTEND_DIST")
if _frontend_dist and os.path.isdir(_frontend_dist):
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
