import os
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from backend.sheet_service import SheetService, DEFAULT_SPREADSHEET_ID

app = FastAPI(
    title="Prediction League Google Sheets Service",
    description="Real-time Google Sheets data extraction, results lookup and tournament leaderboard service",
    version="1.1.0"
)

# Enable CORS for local development and cross-origin access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Get SPREADSHEET_ID from environment if provided
spreadsheet_id = os.environ.get("SPREADSHEET_ID", DEFAULT_SPREADSHEET_ID)
sheet_service = SheetService(spreadsheet_id=spreadsheet_id, cache_ttl_seconds=15)

@app.get("/api/data")
async def get_all_data(fresh: bool = Query(False, description="Force fresh fetch directly from Google Sheets")):
    """Returns complete data payload: overall leaderboard, round standings, match distributions, and sync status."""
    try:
        data = sheet_service.get_data(force=fresh)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/user/{username}")
async def get_user(
    username: str, 
    fresh: bool = Query(False, description="Force fresh fetch directly from Google Sheets")
):
    """Returns detailed profile for a specific participant (case-insensitive lookup, round breakdown, match predictions)."""
    try:
        user_detail = sheet_service.get_user_detail(username, force=fresh)
        if not user_detail:
            raise HTTPException(status_code=404, detail=f"Participant '{username}' not found")
        return user_detail
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/search")
async def search_users(q: str = Query(..., description="Search query string (username or alias)")):
    """Fast autocomplete search for usernames with prefix and substring matching."""
    try:
        results = sheet_service.search_users(query=q)
        return {"query": q, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/matches")
async def get_matches(fresh: bool = Query(False, description="Force fresh fetch directly from Google Sheets")):
    """Returns list of matches for the current round with community voting distributions and outcomes."""
    try:
        data = sheet_service.get_data(force=fresh)
        return {
            "last_updated": data["last_updated"],
            "cached": data["cached"],
            "matches": data["match_distributions"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/rounds/{round_id}")
async def get_round_standings(
    round_id: str,
    fresh: bool = Query(False, description="Force fresh fetch directly from Google Sheets")
):
    """Returns the leaderboard for a specific round (e.g. r1, r2, r3, r4, r5)."""
    try:
        data = sheet_service.get_data(force=fresh)
        standings = data["round_standings"].get(round_id)
        if standings is None:
            raise HTTPException(status_code=404, detail=f"Round '{round_id}' not found")
        
        round_meta = next((r for r in data["rounds"] if r["id"] == round_id), {"id": round_id, "name": round_id})
        return {
            "round": round_meta,
            "standings": standings,
            "last_updated": data["last_updated"]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/refresh")
async def refresh_data():
    """Forces an immediate re-fetch from Google Sheets and updates the cache."""
    try:
        data = sheet_service.get_data(force=True)
        return {
            "status": "success",
            "message": "Data successfully refreshed from Google Sheets",
            "last_updated": data["last_updated"],
            "total_participants": data["total_participants"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Mount frontend directory
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.get("/")
    async def serve_index():
        return FileResponse(os.path.join(frontend_dir, "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
