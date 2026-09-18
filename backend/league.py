"""Turn the organizer's form-responses sheet into rounds, results and standings.

How the organizer lays out "Form Responses 1" (10 matches per round):
  row 1, C..L   current form questions, e.g. "LC R3 [Peterborough vs Barnsley]"
  row 1, P..Y   answer key for the round being scored
  A / B         submission timestamp / username; C..L picks (Home/Draw/Away)
  N / O         username as corrected by the organizer / round points
  AA, AB..AK    written on the FIRST row of a round once it is scored:
                tag ("PL MD4") and results ("Aston Villa 1 - 2 Nott'm Forest")

A round with a tag row is final. Everything after the last final round is either the
tail of that round, the round currently being played, or (briefly) a finished round the
organizer has not published yet. Those are separated by submission gaps and by whether
the organizer has already filled the points column.
"""
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from openpyxl.utils import column_index_from_string, get_column_letter

from backend.live import espn_window, format_score, months_between, outcome_from_scores
from backend.sheet import Grid, as_datetime

OUTCOMES = ("Home", "Draw", "Away")
PICK_ALIASES = {"home": "Home", "1": "Home", "draw": "Draw", "x": "Draw", "away": "Away", "2": "Away"}
PICK_CODES = {"Home": "H", "Draw": "D", "Away": "A", None: "-"}

SPLIT_GAP = timedelta(hours=30)          # longest pause inside a round so far: 24h; shortest between rounds: 32h
SCORED_SPLIT_GAP = timedelta(hours=3)    # scored rows followed by unscored rows after a pause = new round

COMPETITIONS = {
    "PL": ("Premier League", "league"),
    "UCL": ("Champions League", "europe"),
    "UEL": ("Europa League", "europe"),
    "UECL": ("Conference League", "europe"),
    "LC": ("League Cup", "cup"),
    "EFL": ("League Cup", "cup"),
    "FA": ("FA Cup", "cup"),
    "CS": ("Community Shield", "cup"),
}

HEADER_RE = re.compile(r"^(?P<tag>.*?)\s*\[(?P<title>.+)\]\s*$")
VS_RE = re.compile(r"\s+(?:vs?\.?)\s+", re.IGNORECASE)
RESULT_RE = re.compile(
    r"^(?P<home>.+?)\s+(?P<hs>\d+)(?:\s*\((?P<hp>\d+)\))?\s*[-–]\s*(?P<as>\d+)(?:\s*\((?P<ap>\d+)\))?\s+(?P<away>.+)$"
)
TAG_RE = re.compile(r"^[A-Za-z]{2,5}\s*[A-Za-z0-9/ ]+$")

LiveResolver = Callable[[str, List[Dict[str, str]], Optional[datetime]], List[Optional[Dict[str, Any]]]]


# ---------------------------------------------------------------- small parsers

def col_offset(col: str, offset: int) -> str:
    return get_column_letter(column_index_from_string(col) + offset)


def normalize_pick(value: Any) -> Optional[str]:
    if value is None:
        return None
    return PICK_ALIASES.get(str(value).strip().lower())


def clean_username(raw: Any) -> str:
    name = re.sub(r"^/?u/", "", str(raw).strip(), flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", name).strip()


def user_key(name: str) -> str:
    return clean_username(name).lower()


def split_title(title: str) -> Tuple[Optional[str], Optional[str]]:
    parts = VS_RE.split(title.strip(), maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return None, None


def describe_tag(tag: Optional[str]) -> Dict[str, Any]:
    if not tag:
        return {"code": None, "competition": "Unknown", "category": "other", "stage": None}
    m = re.match(r"^([A-Za-z]+)\s*(.*)$", tag.strip())
    code, rest = (m.group(1).upper(), m.group(2).strip()) if m else (tag.upper(), "")
    competition, category = COMPETITIONS.get(code, (code, "other"))
    stage = rest or None
    if re.fullmatch(r"MD\s*\d+", rest, re.IGNORECASE):
        stage = "Matchday " + re.sub(r"\D", "", rest)
    elif re.fullmatch(r"R\s*\d+", rest, re.IGNORECASE):
        stage = "Round " + re.sub(r"\D", "", rest)
    else:
        stage = {"QF": "Quarter-finals", "SF": "Semi-finals", "F": "Final", "PO": "Play-offs"}.get(rest.upper(), stage)
    return {"code": code, "competition": competition, "category": category, "stage": stage}


def parse_result(text: Any) -> Dict[str, Any]:
    text = str(text).strip()
    m = RESULT_RE.match(text)
    if not m:
        return {"home": None, "away": None, "score": None, "outcome": None, "raw": text}
    hs, as_ = int(m["hs"]), int(m["as"])
    hp = int(m["hp"]) if m["hp"] else None
    ap = int(m["ap"]) if m["ap"] else None
    return {
        "home": m["home"].strip(),
        "away": m["away"].strip(),
        "score": format_score(hs, as_, hp, ap),
        "outcome": outcome_from_scores(hs, as_, hp, ap),
        "raw": text,
    }


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.strftime("%Y-%m-%dT%H:%M:%S")
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- sheet layout

class Layout:
    def __init__(self, grid: Grid):
        header = grid.get(1, {})
        count = 0
        while header.get(col_offset("C", count)):
            count += 1
        self.match_count = count or 10
        self.pick_cols = [col_offset("C", i) for i in range(self.match_count)]
        last_pick = self.pick_cols[-1]
        self.name_col = col_offset(last_pick, 2)          # N
        self.points_col = col_offset(last_pick, 3)        # O
        self.key_cols = [col_offset(last_pick, 4 + i) for i in range(self.match_count)]  # P..Y
        self.tag_col = col_offset(self.key_cols[-1], 2)   # AA
        self.result_cols = [col_offset(self.tag_col, 1 + i) for i in range(self.match_count)]  # AB..AK

        self.header_tag: Optional[str] = None
        self.header_matches: List[Dict[str, Any]] = []
        for col in self.pick_cols:
            raw = str(header.get(col, ""))
            m = HEADER_RE.match(raw)
            tag, title = (m["tag"].strip() or None, m["title"].strip()) if m else (None, raw.strip())
            self.header_tag = self.header_tag or tag
            home, away = split_title(title)
            self.header_matches.append({"title": title, "home": home, "away": away})
        self.answer_key = [normalize_pick(header.get(c)) for c in self.key_cols]


# ---------------------------------------------------------------- entries & segmentation

def read_entries(grid: Grid, layout: Layout) -> List[Dict[str, Any]]:
    entries = []
    for r in sorted(grid):
        if r == 1:
            continue
        row = grid[r]
        raw_name = row.get(layout.name_col) or row.get("B")
        submitted = as_datetime(row.get("A"))
        if not raw_name or not submitted or normalize_pick(raw_name) or not clean_username(raw_name):
            continue
        entries.append({
            "row": r,
            "submitted": submitted,
            "name": clean_username(raw_name),
            "key": user_key(str(raw_name)),
            "picks": [normalize_pick(row.get(c)) for c in layout.pick_cols],
            "sheet_points": _number(row.get(layout.points_col)),
        })
    return entries


def is_marker(row: Dict[str, Any], layout: Layout) -> bool:
    tag = row.get(layout.tag_col)
    if not isinstance(tag, str) or tag.upper() in ("H", "D", "A") or not TAG_RE.match(tag):
        return False
    return any(isinstance(row.get(c), str) for c in layout.result_cols)


def split_unmarked(entries: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    segments: List[List[Dict[str, Any]]] = []
    for e in entries:
        if segments:
            prev = segments[-1][-1]
            gap = e["submitted"] - prev["submitted"]
            scored_break = prev["sheet_points"] is not None and e["sheet_points"] is None and gap >= SCORED_SPLIT_GAP
            if gap < SPLIT_GAP and not scored_break:
                segments[-1].append(e)
                continue
        segments.append([e])
    return segments


# ---------------------------------------------------------------- builder

def dedupe_latest(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """If someone submitted twice in a round, the latest submission counts."""
    latest: Dict[str, Dict[str, Any]] = {}
    for e in entries:
        latest[e["key"]] = e
    return sorted(latest.values(), key=lambda e: e["row"])


def distribution(entries: List[Dict[str, Any]], index: int) -> Dict[str, int]:
    counts = Counter(e["picks"][index] for e in entries if e["picks"][index])
    return {"home": counts["Home"], "draw": counts["Draw"], "away": counts["Away"], "total": sum(counts.values())}


def build_league(
    grid: Grid,
    live: Optional[LiveResolver] = None,
    snapshots: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    snapshots = snapshots or {}
    warnings: List[str] = []
    layout = Layout(grid)
    entries = read_entries(grid, layout)

    marker_rows = [e["row"] for e in entries if is_marker(grid[e["row"]], layout)]
    segments: List[Dict[str, Any]] = []  # {"entries", "marker"}

    if marker_rows:
        for i, m in enumerate(marker_rows):
            upper = marker_rows[i + 1] if i + 1 < len(marker_rows) else None
            seg = [e for e in entries if (e["row"] >= m or (i == 0 and e["row"] < m)) and (upper is None or e["row"] < upper)]
            if upper is None:
                parts = split_unmarked(seg)
                segments.append({"entries": parts[0], "marker": m})
                segments.extend({"entries": p, "marker": None} for p in parts[1:])
            else:
                segments.append({"entries": seg, "marker": m})
    else:
        segments.extend({"entries": p, "marker": None} for p in split_unmarked(entries))

    marked_tags = {str(grid[s["marker"]][layout.tag_col]).strip().upper() for s in segments if s["marker"]}
    if layout.header_tag:
        header_is_new = layout.header_tag.strip().upper() not in marked_tags
    else:
        # No "TAG [..]" in the form questions: compare fixtures with the last published round instead.
        last_marker = max((s["marker"] for s in segments if s["marker"]), default=None)
        last_titles = {parse_result(grid[last_marker].get(c, ""))["home"] for c in layout.result_cols} if last_marker else set()
        header_homes = {m["home"] for m in layout.header_matches if m["home"]}
        header_is_new = bool(header_homes) and header_homes != last_titles
    unmarked_idx = [i for i, s in enumerate(segments) if not s["marker"]]

    if header_is_new and not unmarked_idx:
        segments.append({"entries": [], "marker": None})  # new form is open, no submissions yet
        unmarked_idx.append(len(segments) - 1)
    open_idx = unmarked_idx[-1] if (unmarked_idx and header_is_new) else None

    last_final_outcomes: Optional[List[Optional[str]]] = None
    rounds: List[Dict[str, Any]] = []
    round_entries: List[List[Dict[str, Any]]] = []
    new_snapshot: Optional[Tuple[str, Dict[str, Any]]] = None

    for i, seg in enumerate(segments):
        number = i + 1
        seg_entries = dedupe_latest(seg["entries"])
        first_submission = seg_entries[0]["submitted"] if seg_entries else None
        snap_key = _iso(min(e["submitted"] for e in seg["entries"])) if seg["entries"] else "empty"

        if seg["marker"]:
            row = grid[seg["marker"]]
            tag = str(row[layout.tag_col]).strip()
            results = [parse_result(row.get(c, "")) for c in layout.result_cols]
            matches = []
            for idx, res in enumerate(results):
                matches.append({
                    "home": res["home"], "away": res["away"],
                    "title": f"{res['home']} vs {res['away']}" if res["home"] else res["raw"] or f"Match {idx + 1}",
                    "score": res["score"], "outcome": res["outcome"],
                    "status": "final" if res["outcome"] else "void",
                    "detail": "FT" if res["outcome"] else None,
                    "kickoff": None, "confirmed": True,
                })
            last_final_outcomes = [m["outcome"] for m in matches]
            status = "final"
            use_sheet_points = True
        elif i == open_idx:
            tag = layout.header_tag
            matches = [dict(m, score=None, outcome=None, status="unknown", detail=None, kickoff=None, confirmed=False)
                       for m in layout.header_matches]
            info = describe_tag(tag)
            resolved: List[Optional[Dict[str, Any]]] = [None] * len(matches)
            window = espn_window(info["code"], first_submission, now)
            live_feed = None
            if window:
                live_feed = {"league": window["slug"], "dates": f"{window['start']:%Y%m%d}-{window['end']:%Y%m%d}",
                             "months": months_between(window["start"], window["end"]),
                             "earliest": _iso(window["earliest"]), "server_ok": False}
            if live and info["code"]:
                try:
                    resolved = live(info["code"], matches, first_submission)
                    if live_feed:
                        live_feed["server_ok"] = True
                except Exception as exc:  # live scores are a bonus, never fatal; the browser retries
                    warnings.append(f"Live scores unavailable on the server ({exc}); browsers load them directly.")
            key = layout.answer_key
            # Row 1 holds the key of whichever round the organizer scored last. Trust it only once
            # this round's rows have points filled in, and never if it repeats the previous results.
            key_is_stale = (last_final_outcomes is not None and key == last_final_outcomes) or not any(
                e["sheet_points"] is not None for e in seg_entries)
            for m, ev, key_outcome in zip(matches, resolved, key):
                if ev:
                    m.update(score=ev["score"], outcome=ev["outcome"], status=ev["status"], detail=ev["detail"],
                             kickoff=_iso(ev["kickoff"]))
                if key_outcome and not key_is_stale and m["status"] not in ("scheduled", "live"):
                    m.update(outcome=key_outcome, status="final", confirmed=True)
            states = {m["status"] for m in matches}
            if states <= {"final", "postponed", "void"} and "final" in states:
                status = "completed"
            elif "live" in states or "final" in states:
                status = "live"
            else:
                status = "upcoming"
            use_sheet_points = False
            new_snapshot = (snap_key, {"tag": tag, "matches": [
                {k: m[k] for k in ("home", "away", "title", "score", "outcome", "status", "detail", "kickoff")}
                for m in matches]})
        else:
            snap = snapshots.get(snap_key)
            tag = snap["tag"] if snap else None
            if snap:
                matches = [dict(m, confirmed=False) for m in snap["matches"]]
            else:
                matches = [{"home": None, "away": None, "title": f"Match {idx + 1}", "score": None, "outcome": None,
                            "status": "unknown", "detail": None, "kickoff": None, "confirmed": False}
                           for idx in range(layout.match_count)]
            status = "awaiting"
            use_sheet_points = True
            if not snap:
                warnings.append(f"Round {number} finished but has no results row yet; showing the organizer's points only.")

        info = describe_tag(tag)
        if i != open_idx:
            live_feed = None
        scored_points: Dict[str, Optional[float]] = {}
        live_points: Dict[str, int] = {}
        for e in seg_entries:
            computed = sum(1 for p, m in zip(e["picks"], matches) if p and m["status"] == "final" and p == m["outcome"])
            provisional = sum(1 for p, m in zip(e["picks"], matches) if p and m["status"] == "live" and p == m["outcome"])
            if use_sheet_points and e["sheet_points"] is not None:
                scored_points[e["key"]] = e["sheet_points"]
                if seg["marker"] and any(m["outcome"] for m in matches) and e["sheet_points"] != computed:
                    warnings.append(f"Round {number}: sheet gives {e['name']} {e['sheet_points']:g} pts, results say {computed}.")
            elif status == "awaiting" and not snapshots.get(snap_key):
                scored_points[e["key"]] = None
            elif not any(m["status"] == "final" for m in matches):
                scored_points[e["key"]] = None  # nothing decided yet
            else:
                scored_points[e["key"]] = float(computed)
            live_points[e["key"]] = provisional

        for idx, m in enumerate(matches):
            m["index"] = idx
            m["dist"] = distribution(seg_entries, idx)
            decided = m["status"] in ("final", "live") and m["outcome"]
            m["correct_pct"] = (round(100 * m["dist"][m["outcome"].lower()] / m["dist"]["total"])
                                if decided and m["dist"]["total"] else None)

        scores = [v for v in scored_points.values() if v is not None]
        has_results = any(m["status"] == "final" for m in matches) or (status == "awaiting" and bool(scores))
        rounds.append({
            "id": f"r{number}",
            "number": number,
            "tag": tag,
            **info,
            "status": status,
            "official": status == "final",
            "matches": matches,
            "entries": len(seg_entries),
            "opened": _iso(first_submission),
            "live_feed": live_feed,
            "first_kickoff": min((m["kickoff"] for m in matches if m.get("kickoff")), default=None),
            "stats": {
                "average": round(sum(scores) / len(scores), 2) if scores and has_results else None,
                "top": max(scores) if scores and has_results else None,
                "perfect": sum(1 for s in scores if s == len(matches)) if has_results else 0,
            },
            "_points": scored_points,
            "_live": live_points,
            "_has_results": has_results,
        })
        round_entries.append(seg_entries)

    players = build_players(rounds, round_entries)
    picks = {
        r["id"]: {e["key"]: "".join(PICK_CODES[p] for p in e["picks"]) for e in ents}
        for r, ents in zip(rounds, round_entries)
    }
    for r in rounds:
        for k in ("_points", "_live", "_has_results"):
            r.pop(k)

    current = rounds[open_idx]["id"] if open_idx is not None else (rounds[-1]["id"] if rounds else None)
    return {
        "current_round": current,
        "rounds": rounds,
        "players": players,
        "picks": picks,
        "warnings": warnings,
        "snapshot": new_snapshot,
    }


def competition_ranks(items: List[Dict[str, Any]], field: str) -> Dict[str, int]:
    ranks, prev_value, prev_rank = {}, None, 0
    ordered = sorted(items, key=lambda p: -p[field])
    for pos, p in enumerate(ordered, 1):
        if p[field] != prev_value:
            prev_rank, prev_value = pos, p[field]
        ranks[p["key"]] = prev_rank
    return ranks


def build_players(rounds: List[Dict[str, Any]], round_entries: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    names: Dict[str, Counter] = defaultdict(Counter)
    for ents in round_entries:
        for e in ents:
            names[e["key"]][e["name"]] += 1

    players = []
    for key, variants in names.items():
        name = max(variants.items(), key=lambda kv: (kv[1], any(c.isupper() for c in kv[0])))[0]
        per_round: Dict[str, Optional[float]] = {}
        confirmed = unofficial = 0.0
        live_pts = 0
        played = correct_total = decided_total = 0
        best = None
        for r, ents in zip(rounds, round_entries):
            if key not in r["_points"]:
                continue
            played += 1
            pts = r["_points"][key]
            per_round[r["id"]] = pts
            live_pts += r["_live"].get(key, 0)
            if pts is None:
                continue
            if r["official"]:
                confirmed += pts
            else:
                unofficial += pts
            if r["_has_results"]:
                decided = sum(1 for m in r["matches"] if m["status"] == "final") or len(r["matches"])
                decided_total += decided
                correct_total += pts
                if best is None or pts > best["points"]:
                    best = {"round": r["id"], "points": pts}
        players.append({
            "key": key,
            "name": name,
            "aliases": sorted(variants) if len(variants) > 1 else [],
            "total": confirmed + unofficial,
            "confirmed": confirmed,
            "live": live_pts,
            "rounds": per_round,
            "played": played,
            "accuracy": round(100 * correct_total / decided_total) if decided_total else None,
            "best": best,
        })

    # Movement: compare with the table before the latest round that has any results.
    latest = next((r for r in reversed(rounds) if r["_has_results"]), None)
    ranks = competition_ranks(players, "total")
    if latest:
        for p in players:
            p["_before"] = p["total"] - (p["rounds"].get(latest["id"]) or 0)
        before = competition_ranks([p for p in players if latest["id"] not in p["rounds"] or p["played"] > 1] or players, "_before")
    else:
        before = {}
    for p in players:
        p["rank"] = ranks[p["key"]]
        p["prev_rank"] = before.get(p["key"])
        p["movement"] = (p["prev_rank"] - p["rank"]) if p["prev_rank"] else None
        p.pop("_before", None)

    players.sort(key=lambda p: (p["rank"], p["name"].lower()))
    return players
