from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import angelone as angelone_api
from backend.api import chart as chart_api
from backend.api import config as config_api
from backend.api import expiry as expiry_api
from backend.api import expiry_level_5 as expiry_level_5_api
from backend.api import history as history_api
from backend.api import logs as logs_api
from backend.api import scan as scan_api
from backend.api import scanner as scanner_api
from backend.api import top_bottom as top_bottom_api
from backend.api import tradingview as tradingview_api
from backend.core import log_buffer
from backend.core.config import settings
from backend.core.database import init_db
from backend.services import provider_factory

logging.basicConfig(level=settings.log_level)
log_buffer.install()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    await provider_factory.startup()
    try:
        yield
    finally:
        await provider_factory.shutdown()


app = FastAPI(title="NIFTY 200 Scanner", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5180",
    "http://127.0.0.1:5180",
    "https://stockscanner-1-c0hl.onrender.com",
],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(scan_api.router)
app.include_router(history_api.router)
app.include_router(config_api.router)
app.include_router(scanner_api.router)
app.include_router(expiry_api.router)
app.include_router(expiry_level_5_api.router)
app.include_router(angelone_api.router)
app.include_router(tradingview_api.router)
app.include_router(logs_api.router)
app.include_router(chart_api.router)
app.include_router(top_bottom_api.router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
