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
    # Sort by: has uppercase character, then longest, then first
    return max(variants, key=lambda n: (any(c.isupper() for c in n), len(n)))

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

        # 2. Parse matches & actual results from row 1 of Form Responses 1
        r1 = form_rows.get(1, {})
        match_cols = ["C", "D", "E", "F", "G", "H", "I", "J", "K", "L"]
        actual_cols = ["P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y"]

        matches = []
        for m_col, a_col in zip(match_cols, actual_cols):
            title = r1.get(m_col, "").strip()
            actual = r1.get(a_col, "").strip()
            if title:
                short_title = title
                if "[" in title and "]" in title:
                    short_title = title.split("[")[1].split("]")[0]
                matches.append({
                    "col": m_col,
                    "raw_title": title,
                    "title": short_title,
                    "actual": actual
                })

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

        # 3. Parse Round 1-4 scores from Sheet1
        round_definitions = [
            {"id": "r1", "name": "Round 1 (PL MD1)", "user_col": "A", "score_col": "B"},
            {"id": "r2", "name": "Round 2 (LC R2)", "user_col": "D", "score_col": "E"},
            {"id": "r3", "name": "Round 3 (PL MD2)", "user_col": "G", "score_col": "H"},
            {"id": "r4", "name": "Round 4 (PL MD3)", "user_col": "J", "score_col": "K"},
        ]

        raw_rounds_standings: Dict[str, Dict[str, float]] = {}

        for rd in round_definitions:
            r_id = rd["id"]
            scores_by_lower: Dict[str, float] = {}
            for r_num in range(2, 60):
                row = round_rows.get(r_num, {})
                u = row.get(rd["user_col"], "").strip()
                s = row.get(rd["score_col"], "").strip()
                if u:
                    k = register_user(u)
                    try:
                        sc = float(s)
                    except ValueError:
                        sc = 0.0
                    # If duplicate in same round, take max
                    scores_by_lower[k] = max(scores_by_lower.get(k, 0.0), sc)

            raw_rounds_standings[r_id] = scores_by_lower

        # 4. Parse Round 5 (UCL MD1) from Form Responses 1 (rows 174+)
        r5_scores_by_lower: Dict[str, float] = {}
        r5_predictions_by_lower: Dict[str, List[Dict[str, Any]]] = {}
        vote_counts = {
            m["title"]: {"Home": 0, "Draw": 0, "Away": 0, "Total": 0, "actual": m["actual"]}
            for m in matches
        }

        # Submissions for Round 5
        for r_num in sorted(form_rows.keys()):
            if r_num < 174:
                continue
            row = form_rows[r_num]
            u = row.get("B", "").strip()
            if not u:
                continue
            k = register_user(u)

            user_score = 0
            preds = []
            for m in matches:
                pred_val = row.get(m["col"], "").strip()
                actual_val = m["actual"]
                is_correct = bool(pred_val and actual_val and pred_val.lower() == actual_val.lower())
                point = 1 if is_correct else 0
                user_score += point

                if pred_val in vote_counts[m["title"]]:
                    vote_counts[m["title"]][pred_val] += 1
                    vote_counts[m["title"]]["Total"] += 1

                preds.append({
                    "match": m["title"],
                    "prediction": pred_val,
                    "actual": actual_val,
                    "correct": is_correct,
                    "points": point
                })

            r5_scores_by_lower[k] = float(user_score)
            r5_predictions_by_lower[k] = preds

        raw_rounds_standings["r5"] = r5_scores_by_lower

        # 5. Check Sheet2 (Overall Leaderboard) for historical participants
        for r_num in range(1, 250):
            row = overall_rows.get(r_num, {})
            u = row.get("M", "").strip()
            if u:
                register_user(u)

        # 6. Build unified Canonical User Profiles
        all_canonical_keys = list(user_variants.keys())
        overall_leaderboard = []

        for k in all_canonical_keys:
            variants = user_variants[k]
            display_name = pick_canonical_name(variants)

            # Round breakdown
            round_breakdown = {}
            for rd in round_definitions:
                round_breakdown[rd["id"]] = raw_rounds_standings[rd["id"]].get(k)
            round_breakdown["r5"] = r5_scores_by_lower.get(k)

            # Calculate total score as sum of all participating rounds
            total_sc = sum(sc for sc in round_breakdown.values() if sc is not None)
            base_sc = sum(sc for rid, sc in round_breakdown.items() if rid != "r5" and sc is not None)
            r5_sc = r5_scores_by_lower.get(k, 0.0)

            overall_leaderboard.append({
                "username": display_name,
                "canonical_key": k,
                "aliases": variants if len(variants) > 1 else [],
                "total_score": round(total_sc, 1),
                "base_score": round(base_sc, 1),
                "r5_score": round(r5_sc, 1),
                "round_scores": round_breakdown,
                "has_r5_predictions": k in r5_predictions_by_lower
            })

        # Sort overall leaderboard by total_score desc, then r5_score desc, then username asc
        overall_leaderboard.sort(key=lambda x: (-x["total_score"], -x["r5_score"], x["username"].lower()))
        for idx, item in enumerate(overall_leaderboard, 1):
            item["rank"] = idx

        # Build clean round standings with canonical names
        round_lists: Dict[str, List[Dict[str, Any]]] = {}
        for r_id in ["r1", "r2", "r3", "r4", "r5"]:
            scores_map = raw_rounds_standings.get(r_id, {})
            standings = []
            for k, sc in scores_map.items():
                display_name = pick_canonical_name(user_variants[k])
                standings.append({"username": display_name, "canonical_key": k, "score": sc})
            standings.sort(key=lambda x: (-x["score"], x["username"].lower()))
            for idx, item in enumerate(standings, 1):
                item["rank"] = idx
            round_lists[r_id] = standings

        # 7. Calculate Match Distributions
        match_distributions = []
        for m in matches:
            t = m["title"]
            stats = vote_counts[t]
            tot = stats["Total"] if stats["Total"] > 0 else 1
            h_pct = round((stats["Home"] / tot) * 100, 1)
            d_pct = round((stats["Draw"] / tot) * 100, 1)
            a_pct = round((stats["Away"] / tot) * 100, 1)
            match_distributions.append({
                "match": t,
                "actual": stats["actual"],
                "home": stats["Home"],
                "draw": stats["Draw"],
                "away": stats["Away"],
                "total": stats["Total"],
                "home_pct": h_pct,
                "draw_pct": d_pct,
                "away_pct": a_pct
            })

        rounds_meta = [
            {"id": "r1", "name": "Round 1 (PL MD1)"},
            {"id": "r2", "name": "Round 2 (LC R2)"},
            {"id": "r3", "name": "Round 3 (PL MD2)"},
            {"id": "r4", "name": "Round 4 (PL MD3)"},
            {"id": "r5", "name": "Round 5 (UCL MD1)"},
        ]

        return {
            "spreadsheet_id": self.spreadsheet_id,
            "spreadsheet_url": self.spreadsheet_url,
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_participants": len(overall_leaderboard),
            "rounds": rounds_meta,
            "round_standings": round_lists,
            "leaderboard": overall_leaderboard,
            "match_distributions": match_distributions,
            "r5_predictions": {pick_canonical_name(user_variants[k]): preds for k, preds in r5_predictions_by_lower.items()}
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

        # Build round breakdown list
        rounds_meta = data["rounds"]
        round_breakdown_list = []
        for rm in rounds_meta:
            r_id = rm["id"]
            sc = target["round_scores"].get(r_id)
            round_breakdown_list.append({
                "round_id": r_id,
                "round_name": rm["name"],
                "score": sc,
                "participated": sc is not None
            })

        user_preds = data["r5_predictions"].get(target["username"], [])

        return {
            "username": target["username"],
            "aliases": target.get("aliases", []),
            "rank": target["rank"],
            "total_score": target["total_score"],
            "base_score": target["base_score"],
            "r5_score": target["r5_score"],
            "round_scores": round_breakdown_list,
            "r5_predictions": user_preds,
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
            # Match against display name or any alias
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

        # Sort by starts-with first, then by rank
        results.sort(key=lambda x: (not x["starts"], x["rank"]))
        return results[:limit]
