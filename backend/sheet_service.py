import urllib.request
import zipfile
import io
import xml.etree.ElementTree as ET
import time
from datetime import datetime
import threading
from typing import Dict, List, Any, Optional
from collections import defaultdict

DEFAULT_SPREADSHEET_ID = "1oibdWWMrTXoFXozDIo4jfcukfNNJOfMbrTduzDS0Ji4"

def pick_canonical_name(variants: List[str]) -> str:
    """Select the best display name from case variants (e.g. Qqq666 over qqq666)."""
    if not variants:
        return ""
    return max(variants, key=lambda n: (any(c.isupper() for c in n), len(n)))

# Master archive of historical rounds with their official match titles and outcomes.
# This prevents upcoming rounds in Google Forms from overwriting past match titles and breakdowns.
ARCHIVED_ROUNDS = {
    "r5": {
        "id": "r5",
        "name": "Round 5 (UCL MD1)",
        "status": "completed",
        "user_col": "M",
        "score_col": "N",
        "row_start": 175,
        "row_end": 212,
        "matches": [
            {"title": "Club Brugge vs Aston Villa", "code": "BRU/AVL", "actual": "Away"},
            {"title": "Dortmund vs Villarreal", "code": "BVB/VIL", "actual": "Home"},
            {"title": "Napoli vs Arsenal", "code": "NAP/ARS", "actual": "Away"},
            {"title": "Barcelona vs Feyenoord", "code": "BAR/FEY", "actual": "Home"},
            {"title": "Liverpool vs Atletico Madrid", "code": "LIV/ATM", "actual": "Home"},
            {"title": "Porto vs Manchester City", "code": "POR/MCI", "actual": "Away"},
            {"title": "Real Madrid vs Inter Milan", "code": "RMA/INT", "actual": "Home"},
            {"title": "PSG vs Slovan Bratislava", "code": "PSG/SLB", "actual": "Home"},
            {"title": "Bayern Munich vs Bodo/Glimt", "code": "BAY/BOD", "actual": "Home"},
            {"title": "Manchester United vs Sabah", "code": "MUN/SAB", "actual": "Home"},
        ]
    },
    "r4": {
        "id": "r4",
        "name": "Round 4 (PL MD3)",
        "status": "completed",
        "user_col": "J",
        "score_col": "K",
        "row_start": 135,
        "row_end": 174,
        "matches": [
            {"title": "Ipswich vs Liverpool", "code": "IPS/LIV", "actual": None},
            {"title": "Newcastle vs Bournemouth", "code": "NEW/BOU", "actual": None},
            {"title": "Nottingham Forest vs Tottenham", "code": "NFO/TOT", "actual": None},
            {"title": "Fulham vs Crystal Palace", "code": "FUL/CRY", "actual": None},
            {"title": "Manchester City vs Coventry", "code": "MCI/COV", "actual": None},
            {"title": "Brentford vs Sunderland", "code": "BRE/SUN", "actual": None},
            {"title": "Brighton vs Leeds", "code": "BHA/LEE", "actual": None},
            {"title": "Hull vs Aston Villa", "code": "HUL/AVL", "actual": None},
            {"title": "Everton vs Manchester United", "code": "EVE/MUN", "actual": None},
            {"title": "Arsenal vs Chelsea", "code": "ARS/CHE", "actual": None},
        ]
    }
}

class SheetService:
    def __init__(self, spreadsheet_id: str = DEFAULT_SPREADSHEET_ID, cache_ttl_seconds: int = 15):
        self.spreadsheet_id = spreadsheet_id
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cached_data: Optional[Dict[str, Any]] = None
        self._last_fetch_time: float = 0
        self._lock = threading.Lock()

    @property
    def spreadsheet_url(self) -> str:
        return f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}/edit"

    def get_data(self, force: bool = False) -> Dict[str, Any]:
        """Returns parsed data, refreshing from Google Sheets if forced or cache expired."""
        now = time.time()
        with self._lock:
            if not force and self._cached_data is not None and (now - self._last_fetch_time < self.cache_ttl_seconds):
                data = dict(self._cached_data)
                data["cached"] = True
                data["cache_age_seconds"] = round(now - self._last_fetch_time, 1)
                return data

            # Fetch fresh from Google Sheets
            parsed = self._fetch_and_parse()
            self._cached_data = parsed
            self._last_fetch_time = time.time()
            data = dict(parsed)
            data["cached"] = False
            data["cache_age_seconds"] = 0
            return data

    def _fetch_and_parse(self) -> Dict[str, Any]:
        url = f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}/export?format=xlsx"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
        })

        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                content = response.read()
        except Exception as e:
            raise RuntimeError(f"Failed to fetch data from Google Sheets: {e}")

        zf = zipfile.ZipFile(io.BytesIO(content))

        # 1. Parse shared strings
        shared_strings = []
        if "xl/sharedStrings.xml" in zf.namelist():
            ss_root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in ss_root.findall("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si"):
                txt = "".join(node.text for node in si.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t") if node.text)
                shared_strings.append(txt)

        def parse_sheet(sheet_path: str) -> Dict[int, Dict[str, str]]:
            if sheet_path not in zf.namelist():
                return {}
            root = ET.fromstring(zf.read(sheet_path))
            rows: Dict[int, Dict[str, str]] = {}
            for row in root.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row"):
                r_num = int(row.get("r"))
                row_dict = {}
                for c in row.findall("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c"):
                    ref = c.get("r")
                    col = "".join([ch for ch in ref if ch.isalpha()])
                    t = c.get("t")
                    v = c.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v")
                    val = v.text if v is not None else ""
                    if t == "s" and val != "":
                        val = shared_strings[int(val)]
                    row_dict[col] = val
                rows[r_num] = row_dict
            return rows

        form_rows = parse_sheet("xl/worksheets/sheet1.xml")
        round_rows = parse_sheet("xl/worksheets/sheet2.xml")
        overall_rows = parse_sheet("xl/worksheets/sheet3.xml")

        # Name variant tracker (lowercase -> list of seen raw strings)
        user_variants: Dict[str, List[str]] = defaultdict(list)

        def register_user(raw_name: str) -> str:
            clean = raw_name.strip()
            if not clean:
                return ""
            k = clean.lower()
            if clean not in user_variants[k]:
                user_variants[k].append(clean)
            return k

        # 2. Parse matches for current/active round from Row 0 of Form Responses 1
        r1_header = form_rows.get(1, {})
        match_cols = ["C", "D", "E", "F", "G", "H", "I", "J", "K", "L"]

        active_matches = []
        active_round_name = "Round 6 (PL MD4)"
        for idx, m_col in enumerate(match_cols):
            raw_title = r1_header.get(m_col, "").strip()
            if raw_title:
                if "[" in raw_title and "]" in raw_title:
                    short_title = raw_title.split("[")[1].split("]")[0]
                    round_tag = raw_title.split("[")[0].strip()
                    if round_tag:
                        active_round_name = f"Round 6 ({round_tag})"
                else:
                    short_title = raw_title
                active_matches.append({
                    "col": m_col,
                    "title": short_title,
                    "raw_title": raw_title,
                    "actual": None  # Active/upcoming round matches are pending
                })

        # 3. Parse Round 1-5 official standings from Sheet1
        round_definitions = [
            {"id": "r1", "name": "Round 1 (PL MD1)", "user_col": "A", "score_col": "B", "status": "completed"},
            {"id": "r2", "name": "Round 2 (LC R2)", "user_col": "D", "score_col": "E", "status": "completed"},
            {"id": "r3", "name": "Round 3 (PL MD2)", "user_col": "G", "score_col": "H", "status": "completed"},
            {"id": "r4", "name": "Round 4 (PL MD3)", "user_col": "J", "score_col": "K", "status": "completed"},
            {"id": "r5", "name": "Round 5 (UCL MD1)", "user_col": "M", "score_col": "N", "status": "completed"},
        ]

        raw_rounds_standings: Dict[str, Dict[str, float]] = {}

        for rd in round_definitions:
            r_id = rd["id"]
            scores_by_lower: Dict[str, float] = {}
            for r_num in range(2, 65):
                row = round_rows.get(r_num, {})
                u = row.get(rd["user_col"], "").strip()
                s = row.get(rd["score_col"], "").strip()
                if u:
                    k = register_user(u)
                    try:
                        sc = float(s)
                    except ValueError:
                        sc = 0.0
                    scores_by_lower[k] = max(scores_by_lower.get(k, 0.0), sc)

            raw_rounds_standings[r_id] = scores_by_lower

        # 4. Parse Predictions by Round
        # We store predictions per round in `round_predictions[round_id][user_lower]`
        round_predictions: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(dict)
        round_distributions: Dict[str, List[Dict[str, Any]]] = {}

        # 4A. Parse Round 5 (UCL MD1) predictions (rows 175 to 212)
        r5_matches = ARCHIVED_ROUNDS["r5"]["matches"]
        r5_votes = {m["title"]: {"Home": 0, "Draw": 0, "Away": 0, "Total": 0, "actual": m["actual"]} for m in r5_matches}

        for r_num in range(175, 213):
            row = form_rows.get(r_num, {})
            u = row.get("B", "").strip()
            if not u:
                continue
            k = register_user(u)

            user_preds = []
            for idx, m_col in enumerate(match_cols):
                if idx >= len(r5_matches):
                    break
                m = r5_matches[idx]
                pred_val = row.get(m_col, "").strip()
                actual_val = m["actual"]
                is_correct = bool(pred_val and actual_val and pred_val.lower() == actual_val.lower())
                point = 1 if is_correct else 0

                if pred_val in r5_votes[m["title"]]:
                    r5_votes[m["title"]][pred_val] += 1
                    r5_votes[m["title"]]["Total"] += 1

                user_preds.append({
                    "match": m["title"],
                    "prediction": pred_val,
                    "actual": actual_val,
                    "correct": is_correct,
                    "points": point
                })

            round_predictions["r5"][k] = user_preds

        # Build R5 distributions
        r5_dist = []
        for m in r5_matches:
            stats = r5_votes[m["title"]]
            tot = stats["Total"] if stats["Total"] > 0 else 1
            r5_dist.append({
                "match": m["title"],
                "actual": stats["actual"],
                "home": stats["Home"],
                "draw": stats["Draw"],
                "away": stats["Away"],
                "total": stats["Total"],
                "home_pct": round((stats["Home"] / tot) * 100, 1),
                "draw_pct": round((stats["Draw"] / tot) * 100, 1),
                "away_pct": round((stats["Away"] / tot) * 100, 1)
            })
        round_distributions["r5"] = r5_dist

        # 4B. Parse Round 6 (PL MD4) predictions (rows 213+)
        r6_votes = {m["title"]: {"Home": 0, "Draw": 0, "Away": 0, "Total": 0, "actual": None} for m in active_matches}
        r6_scores: Dict[str, float] = {}

        for r_num in sorted(form_rows.keys()):
            if r_num < 213:
                continue
            row = form_rows[r_num]
            u = row.get("B", "").strip()
            if not u or u in ["Home", "Draw", "Away"]:
                continue
            k = register_user(u)

            user_preds = []
            for m in active_matches:
                pred_val = row.get(m["col"], "").strip()
                if pred_val in r6_votes[m["title"]]:
                    r6_votes[m["title"]][pred_val] += 1
                    r6_votes[m["title"]]["Total"] += 1

                user_preds.append({
                    "match": m["title"],
                    "prediction": pred_val,
                    "actual": None,  # Pending
                    "correct": None,
                    "points": 0
                })

            round_predictions["r6"][k] = user_preds
            r6_scores[k] = 0.0

        raw_rounds_standings["r6"] = r6_scores

        # Build R6 distributions
        r6_dist = []
        for m in active_matches:
            stats = r6_votes[m["title"]]
            tot = stats["Total"] if stats["Total"] > 0 else 1
            r6_dist.append({
                "match": m["title"],
                "actual": None,
                "home": stats["Home"],
                "draw": stats["Draw"],
                "away": stats["Away"],
                "total": stats["Total"],
                "home_pct": round((stats["Home"] / tot) * 100, 1),
                "draw_pct": round((stats["Draw"] / tot) * 100, 1),
                "away_pct": round((stats["Away"] / tot) * 100, 1)
            })
        round_distributions["r6"] = r6_dist

        # 5. Check Sheet2 (Overall Leaderboard) for any participants not yet seen
        for r_num in range(1, 250):
            row = overall_rows.get(r_num, {})
            u = row.get("M", "").strip()
            if u:
                register_user(u)

        # 6. Build unified Canonical User Profiles
        all_canonical_keys = list(user_variants.keys())
        overall_leaderboard = []

        all_round_ids = ["r1", "r2", "r3", "r4", "r5", "r6"]

        for k in all_canonical_keys:
            variants = user_variants[k]
            display_name = pick_canonical_name(variants)

            # Round breakdown
            round_breakdown = {}
            for rid in all_round_ids:
                round_breakdown[rid] = raw_rounds_standings.get(rid, {}).get(k)

            # Calculate total score across all completed rounds
            total_sc = sum(sc for rid, sc in round_breakdown.items() if sc is not None)
            base_sc = sum(sc for rid, sc in round_breakdown.items() if rid not in ["r5", "r6"] and sc is not None)

            overall_leaderboard.append({
                "username": display_name,
                "canonical_key": k,
                "aliases": variants if len(variants) > 1 else [],
                "total_score": round(total_sc, 1),
                "base_score": round(base_sc, 1),
                "round_scores": round_breakdown,
                "has_active_predictions": k in round_predictions["r6"],
                "has_r5_predictions": k in round_predictions["r5"]
            })

        # Sort overall leaderboard by total_score desc, then username asc
        overall_leaderboard.sort(key=lambda x: (-x["total_score"], x["username"].lower()))
        for idx, item in enumerate(overall_leaderboard, 1):
            item["rank"] = idx

        # Build clean round standings with canonical names
        round_lists: Dict[str, List[Dict[str, Any]]] = {}
        for r_id in all_round_ids:
            scores_map = raw_rounds_standings.get(r_id, {})
            standings = []
            for k, sc in scores_map.items():
                display_name = pick_canonical_name(user_variants[k])
                standings.append({
                    "username": display_name,
                    "canonical_key": k,
                    "score": sc,
                    "submitted": k in round_predictions.get(r_id, {})
                })
            standings.sort(key=lambda x: (-x["score"], x["username"].lower()))
            for idx, item in enumerate(standings, 1):
                item["rank"] = idx
            round_lists[r_id] = standings

        rounds_meta = [
            {"id": "r1", "name": "Round 1 (PL MD1)", "status": "completed"},
            {"id": "r2", "name": "Round 2 (LC R2)", "status": "completed"},
            {"id": "r3", "name": "Round 3 (PL MD2)", "status": "completed"},
            {"id": "r4", "name": "Round 4 (PL MD3)", "status": "completed"},
            {"id": "r5", "name": "Round 5 (UCL MD1)", "status": "completed"},
            {"id": "r6", "name": active_round_name, "status": "active"},
        ]

        return {
            "spreadsheet_id": self.spreadsheet_id,
            "spreadsheet_url": self.spreadsheet_url,
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_participants": len(overall_leaderboard),
            "active_round_id": "r6",
            "rounds": rounds_meta,
            "round_standings": round_lists,
            "leaderboard": overall_leaderboard,
            "match_distributions": round_distributions.get("r6", []),
            "round_match_distributions": round_distributions,
            "round_predictions": round_predictions
        }

    def get_user_detail(self, username: str, force: bool = False) -> Optional[Dict[str, Any]]:
        """Returns details, stats and predictions for a specific user (case-insensitive lookup)."""
        data = self.get_data(force=force)
        username_lower = username.strip().lower()

        target = None
        for item in data["leaderboard"]:
            if item["canonical_key"] == username_lower or item["username"].lower() == username_lower:
                target = item
                break

        if not target:
            return None

        k = target["canonical_key"]

        # Build round breakdown list
        rounds_meta = data["rounds"]
        round_breakdown_list = []
        for rm in rounds_meta:
            r_id = rm["id"]
            sc = target["round_scores"].get(r_id)
            has_preds = k in data["round_predictions"].get(r_id, {})
            round_breakdown_list.append({
                "round_id": r_id,
                "round_name": rm["name"],
                "score": sc,
                "participated": sc is not None or has_preds,
                "status": rm["status"]
            })

        # Assemble predictions for each round for this user
        user_round_preds = {}
        for r_id, user_map in data["round_predictions"].items():
            if k in user_map:
                user_round_preds[r_id] = user_map[k]

        return {
            "username": target["username"],
            "aliases": target.get("aliases", []),
            "rank": target["rank"],
            "total_score": target["total_score"],
            "base_score": target["base_score"],
            "active_round_id": "r6",
            "round_scores": round_breakdown_list,
            "round_predictions": user_round_preds,
            "r5_predictions": user_round_preds.get("r5", []),
            "total_participants": data["total_participants"],
            "last_updated": data["last_updated"],
            "cached": data["cached"]
        }

    def search_users(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Fast autocomplete search for usernames (case-insensitive)."""
        if not query or not query.strip():
            return []

        data = self.get_data()
        q = query.strip().lower()
        results = []
        for item in data["leaderboard"]:
            u = item["username"]
            aliases = item.get("aliases", [])
            match_display = q in u.lower()
            match_alias = any(q in a.lower() for a in aliases)
            if match_display or match_alias:
                starts = u.lower().startswith(q) or any(a.lower().startswith(q) for a in aliases)
                results.append({
                    "username": u,
                    "aliases": aliases,
                    "rank": item["rank"],
                    "total_score": item["total_score"],
                    "starts": starts
                })

        results.sort(key=lambda x: (not x["starts"], x["rank"]))
        return results[:limit]
