"""Live and final match results from ESPN's public (keyless) scoreboard API."""
import json
import re
import threading
import time
import unicodedata
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

ESPN_SLUGS = {
    "PL": "eng.1",
    "UCL": "uefa.champions",
    "UEL": "uefa.europa",
    "UECL": "uefa.europa.conf",
    "LC": "eng.league_cup",
    "EFL": "eng.league_cup",
    "FA": "eng.fa",
    "CS": "eng.charity",
}

# Organizer shorthand -> words ESPN uses. Applied on word boundaries to a lowercased name.
TEAM_ALIASES = [
    (r"\bman utd\b|\bman united\b", "manchester united"),
    (r"\bman city\b", "manchester city"),
    (r"\bnott'?m\b|\bnotts forest\b", "nottingham"),
    (r"\bspurs\b", "tottenham"),
    (r"\bwolves\b", "wolverhampton"),
    (r"\bsheff\b", "sheffield"),
    (r"\bweds?\b", "wednesday"),
    (r"\butd\b", "united"),
    (r"\bwest brom\b", "west bromwich"),
    (r"\bqpr\b", "queens park rangers"),
    (r"\bmk dons\b", "milton keynes dons"),
    (r"\bb\. ?dortmund\b|\bbvb\b", "borussia dortmund"),
    (r"\bm'gladbach\b|\bgladbach\b", "borussia monchengladbach"),
    (r"\batleti\b", "atletico madrid"),
    (r"\binter\b", "internazionale"),
    (r"\bpsg\b|^paris$", "paris saint germain"),
    (r"\bs\. ?bratislava\b", "slovan bratislava"),
    (r"\bmunchen\b|\bmuenchen\b", "munich"),
    (r"\bleverkusen\b", "bayer leverkusen"),
    (r"\bpsv\b", "psv eindhoven"),
    (r"\bsporting\b", "sporting cp"),
]
STOP_WORDS = {"fc", "afc", "cf", "sc", "ac", "the", "de", "and", "club"}


def team_tokens(name: str) -> set:
    n = unicodedata.normalize("NFKD", name.lower().replace("ø", "o").replace("æ", "ae").replace("ß", "ss"))
    n = "".join(ch for ch in n if not unicodedata.combining(ch))
    for pattern, replacement in TEAM_ALIASES:
        n = re.sub(pattern, replacement, n)
    return set(re.findall(r"[a-z0-9]+", n)) - STOP_WORDS


def _similarity(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def _int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def outcome_from_scores(home: int, away: int, home_pens: Optional[int] = None, away_pens: Optional[int] = None) -> str:
    """Cup ties level after extra time go to the shootout winner (matches the organizer's scoring)."""
    if home == away and home_pens is not None and away_pens is not None and home_pens != away_pens:
        home, away = home_pens, away_pens
    if home > away:
        return "Home"
    if away > home:
        return "Away"
    return "Draw"


def format_score(home: int, away: int, home_pens: Optional[int] = None, away_pens: Optional[int] = None) -> str:
    if home_pens is not None and away_pens is not None:
        return f"{home} ({home_pens}) - {away} ({away_pens})"
    return f"{home} - {away}"


def parse_event(ev: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    comps = ev.get("competitions") or []
    if not comps:
        return None
    competitors = comps[0].get("competitors") or []
    home = next((c for c in competitors if c.get("homeAway") == "home"), None)
    away = next((c for c in competitors if c.get("homeAway") == "away"), None)
    if not home or not away:
        return None

    status_type = (ev.get("status") or {}).get("type") or {}
    name = status_type.get("name", "")
    state = status_type.get("state", "")
    if any(word in name for word in ("POSTPONED", "CANCELED", "CANCELLED", "ABANDONED", "SUSPENDED")):
        status = "postponed"
    elif state == "post" and status_type.get("completed"):
        status = "final"
    elif state == "in":
        status = "live"
    else:
        status = "scheduled"

    hs, as_ = _int(home.get("score")), _int(away.get("score"))
    hp, ap = _int(home.get("shootoutScore")), _int(away.get("shootoutScore"))
    score = outcome = None
    if status in ("live", "final") and hs is not None and as_ is not None:
        score = format_score(hs, as_, hp, ap)
        outcome = outcome_from_scores(hs, as_, hp, ap)

    kickoff = None
    try:
        kickoff = datetime.strptime(ev.get("date", ""), "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    return {
        "home_name": (home.get("team") or {}).get("displayName", ""),
        "away_name": (away.get("team") or {}).get("displayName", ""),
        "kickoff": kickoff,
        "status": status,
        "detail": status_type.get("shortDetail", ""),
        "score": score,
        "outcome": outcome,
    }


class LiveResults:
    def __init__(self, timeout: float = 10):
        self.timeout = timeout
        self._cache: Dict[str, Any] = {}
        self._lock = threading.Lock()

    HOSTS = ("site.api.espn.com", "site.web.api.espn.com")
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/126.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-GB,en;q=0.9",
        "Referer": "https://www.espn.com/",
        "Origin": "https://www.espn.com",
    }

    def _fetch(self, slug: str, start: datetime, end: datetime) -> List[Dict[str, Any]]:
        path = f"/apis/site/v2/sports/soccer/{slug}/scoreboard?dates={start:%Y%m%d}-{end:%Y%m%d}&limit=300"
        last_error: Optional[Exception] = None
        for host in self.HOSTS:
            try:
                req = urllib.request.Request(f"https://{host}{path}", headers=self.HEADERS)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                return [e for e in (parse_event(ev) for ev in data.get("events", [])) if e]
            except Exception as exc:  # try the next host
                last_error = exc
        raise last_error or RuntimeError("ESPN unavailable")

    @staticmethod
    def _ttl_for(events: List[Dict[str, Any]]) -> float:
        """Poll often around kick-off and in play, slowly otherwise."""
        now = datetime.now(timezone.utc)
        busy = any(
            e["status"] == "live" or (e["kickoff"] and abs((e["kickoff"] - now).total_seconds()) < 3 * 3600)
            for e in events
        )
        return 45 if busy else 600

    def events(self, slug: str, start: datetime, end: datetime) -> List[Dict[str, Any]]:
        key = f"{slug}:{start:%Y%m%d}:{end:%Y%m%d}"
        now = time.time()
        with self._lock:
            cached = self._cache.get(key)
        if cached and now - cached[0] < self._ttl_for(cached[1]):
            return cached[1]
        try:
            events = self._fetch(slug, start, end)
        except Exception:
            if cached:
                return cached[1]
            raise
        with self._lock:
            self._cache[key] = (now, events)
        return events

    def resolve(self, competition: str, matches: List[Dict[str, str]], since: Optional[datetime]) -> List[Optional[Dict[str, Any]]]:
        """Find the ESPN fixture for each {home, away} match played on/after `since`."""
        window = espn_window(competition, since)
        if not window or not matches:
            return [None] * len(matches)
        events = self.events(window["slug"], window["start"], window["end"])
        return match_events(matches, events, window["earliest"])


def espn_window(competition: str, since: Optional[datetime], now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """Which scoreboard to read for a round. The browser uses the same window when the server is blocked."""
    slug = ESPN_SLUGS.get(competition or "")
    if not slug:
        return None
    now = now or datetime.now(timezone.utc)
    since = since or (now - timedelta(days=3))
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    return {
        "slug": slug,
        "start": since - timedelta(days=1),
        "end": max(since, now) + timedelta(days=10),
        # Sheet timestamps carry no timezone, so allow a generous margin before the first submission.
        "earliest": since - timedelta(hours=18),
    }


def match_events(matches: List[Dict[str, str]], events: List[Dict[str, Any]], earliest: datetime) -> List[Optional[Dict[str, Any]]]:
    now = datetime.now(timezone.utc)
    resolved = []
    for m in matches:
        home_t, away_t = team_tokens(m.get("home") or ""), team_tokens(m.get("away") or "")
        best, best_key = None, None
        for ev in events:
            if ev["kickoff"] and ev["kickoff"] < earliest:
                continue
            score = min(_similarity(home_t, team_tokens(ev["home_name"])), _similarity(away_t, team_tokens(ev["away_name"])))
            if score < 0.5:
                continue
            key = (-score, ev["kickoff"] or now)
            if best_key is None or key < best_key:
                best, best_key = ev, key
        resolved.append(best)
    return resolved
