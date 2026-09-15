"""Caching layer: keeps one built league payload fresh without blocking requests."""
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from backend.league import build_league, user_key
from backend.live import LiveResults
from backend.sheet import download_xlsx, parse_form_grid

log = logging.getLogger("prediction_league")

DEFAULT_SPREADSHEET_ID = "1oibdWWMrTXoFXozDIo4jfcukfNNJOfMbrTduzDS0Ji4"
SNAPSHOT_LIMIT = 12


def _utc_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class LeagueService:
    def __init__(
        self,
        spreadsheet_id: str = DEFAULT_SPREADSHEET_ID,
        ttl_seconds: float = 60,
        min_force_interval: float = 20,
        data_dir: Optional[str] = None,
        downloader: Optional[Callable[[str], bytes]] = None,
        live: Optional[LiveResults] = None,
    ):
        self.spreadsheet_id = spreadsheet_id
        self.ttl = ttl_seconds
        self.min_force_interval = min_force_interval
        self.downloader = downloader or download_xlsx
        self.live = live if live is not None else LiveResults()
        self.snapshot_path = os.path.join(data_dir, "snapshots.json") if data_dir else None

        self._payload: Optional[Dict[str, Any]] = None
        self._fetched_at = 0.0
        self._last_error: Optional[str] = None
        self._refresh_lock = threading.Lock()
        self._background: Optional[threading.Thread] = None
        self._snapshots = self._load_snapshots()

    @property
    def spreadsheet_url(self) -> str:
        return f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}/edit"

    # ------------------------------------------------------------ snapshots
    def _load_snapshots(self) -> Dict[str, Any]:
        if not self.snapshot_path or not os.path.exists(self.snapshot_path):
            return {}
        try:
            with open(self.snapshot_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            log.warning("Ignoring unreadable snapshot file %s", self.snapshot_path)
            return {}

    def _save_snapshot(self, snapshot) -> None:
        if not snapshot:
            return
        key, value = snapshot
        if self._snapshots.get(key) == value:
            return
        self._snapshots[key] = value
        for old in sorted(self._snapshots)[:-SNAPSHOT_LIMIT]:
            self._snapshots.pop(old)
        if not self.snapshot_path:
            return
        try:
            os.makedirs(os.path.dirname(self.snapshot_path), exist_ok=True)
            tmp = self.snapshot_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._snapshots, f)
            os.replace(tmp, self.snapshot_path)
        except OSError as exc:
            log.warning("Could not persist snapshots: %s", exc)

    # ------------------------------------------------------------ refresh
    def _build(self) -> None:
        content = self.downloader(self.spreadsheet_id)
        grid = parse_form_grid(content)
        league = build_league(grid, live=self.live.resolve if self.live else None, snapshots=self._snapshots)
        self._save_snapshot(league.pop("snapshot"))
        self._payload = league
        self._fetched_at = time.time()
        self._last_error = None

    def refresh(self, max_age: float = 0) -> None:
        with self._refresh_lock:
            if self._payload is not None and time.time() - self._fetched_at < max_age:
                return  # someone else refreshed while we waited for the lock
            try:
                self._build()
            except Exception as exc:
                self._last_error = str(exc) or exc.__class__.__name__
                log.exception("League refresh failed")
                if self._payload is None:
                    raise

    def _refresh_in_background(self) -> None:
        if self._background and self._background.is_alive():
            return
        self._background = threading.Thread(target=self._safe_refresh, daemon=True)
        self._background.start()

    def _safe_refresh(self) -> None:
        try:
            self.refresh()
        except Exception:
            pass

    def warm_up(self) -> None:
        self._refresh_in_background()

    def get(self, force: bool = False) -> Dict[str, Any]:
        age = time.time() - self._fetched_at
        if self._payload is None:
            self.refresh(max_age=self.ttl)
        elif force and age >= self.min_force_interval:
            self.refresh(max_age=self.min_force_interval)
        elif age >= self.ttl:
            self._refresh_in_background()  # serve what we have, update for the next request
        return self._with_meta()

    def _with_meta(self) -> Dict[str, Any]:
        payload = dict(self._payload or {})
        age = time.time() - self._fetched_at
        payload["meta"] = {
            "spreadsheet_url": self.spreadsheet_url,
            "fetched_at": _utc_iso(self._fetched_at),
            "age_seconds": round(age),
            "stale": self._last_error is not None,
            "error": self._last_error,
        }
        return payload

    def player(self, name: str) -> Optional[Dict[str, Any]]:
        data = self.get()
        key = user_key(name)
        player = next((p for p in data["players"] if p["key"] == key), None)
        if not player:
            return None
        rounds = []
        for r in data["rounds"]:
            code = data["picks"].get(r["id"], {}).get(key)
            if code is None:
                continue
            picks = []
            for m, c in zip(r["matches"], code):
                pick = {"H": "Home", "D": "Draw", "A": "Away"}.get(c)
                decided = m["status"] == "final" and m["outcome"]
                picks.append({
                    "match": m["title"], "pick": pick, "result": m["outcome"], "score": m["score"],
                    "status": m["status"], "correct": (pick == m["outcome"]) if decided else None,
                })
            rounds.append({"id": r["id"], "tag": r["tag"], "status": r["status"],
                           "points": player["rounds"].get(r["id"]), "picks": picks})
        return {**player, "round_details": rounds, "meta": data["meta"]}
