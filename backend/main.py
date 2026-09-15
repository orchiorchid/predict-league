import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from backend.service import DEFAULT_SPREADSHEET_ID, LeagueService

logging.basicConfig(level=logging.INFO)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(ROOT, "frontend")

service = LeagueService(
    spreadsheet_id=os.environ.get("SPREADSHEET_ID", DEFAULT_SPREADSHEET_ID),
    ttl_seconds=float(os.environ.get("CACHE_TTL_SECONDS", "60")),
    data_dir=os.environ.get("DATA_DIR", os.path.join(ROOT, "data")),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.environ.get("WARM_UP", "1") == "1":
        service.warm_up()  # first visitor after a cold start should not wait for Google
    yield


app = FastAPI(
    title="Prediction League",
    description="Standings, results and live scores for the Reddit football prediction league.",
    version="2.0.0",
    lifespan=lifespan,
)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])


def _no_store(payload) -> JSONResponse:
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


@app.get("/api/league")
async def league():
    """Everything the site needs: rounds with matches and pick distributions, standings and picks."""
    try:
        return _no_store(await run_in_threadpool(service.get))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Could not load the league sheet: {exc}")


@app.post("/api/refresh")
async def refresh():
    """Re-read the sheet now (throttled so it cannot be used to hammer Google)."""
    try:
        data = await run_in_threadpool(service.get, True)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return _no_store({"meta": data["meta"], "current_round": data["current_round"]})


@app.get("/api/players/{name}")
async def player(name: str):
    try:
        detail = await run_in_threadpool(service.player, name)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if not detail:
        raise HTTPException(status_code=404, detail=f"Player '{name}' not found")
    return _no_store(detail)


@app.get("/api/health")
async def health():
    return {"ok": True}


if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"), headers={"Cache-Control": "no-cache"})
