import urllib.request
import json
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional

class ESPNService:
    """
    Automated service that fetches live and final match results from ESPN's open public API
    without requiring any API keys or tokens.
    """
    LEAGUES = {
        "PL": "eng.1",
        "UCL": "uefa.champions",
        "CUP": "eng.league_cup",
        "FA": "eng.fa"
    }

    def __init__(self, cache_ttl_seconds: int = 60):
        self.cache_ttl = cache_ttl_seconds
        self._cache: Dict[str, Any] = {}
        self._cache_time: Dict[str, float] = {}

    def clean_team_words(self, name: str) -> set:
        n = name.lower()
        replacements = {
            "nott'm": "nottingham",
            "spurs": "tottenham",
            "man utd": "manchester united",
            "man city": "manchester city",
            "wolves": "wolverhampton",
            "west ham": "west ham",
            "newcastle": "newcastle",
            "b. dortmund": "dortmund",
            "borussia dortmund": "dortmund",
            "atleti": "atletico",
            "paris": "paris saint germain",
            "psg": "paris saint germain",
            "inter": "internazionale",
            "bodø/glimt": "bodo glimt",
            "bodo/glimt": "bodo glimt",
            "bayern münchen": "bayern munich"
        }
        for k, v in replacements.items():
            if k in n:
                n = n.replace(k, v)

        stop_words = {
            'fc', 'afc', 'united', 'city', 'town', 'hotspur', 'albion',
            '&', 'and', 'de', 'club', 'wanderers', 'athletic'
        }
        words = set(re.findall(r'[a-z0-9]+', n)) - stop_words
        return words

    def fetch_league_events(self, league_slug: str = "eng.1", days_window: int = 7) -> List[Dict[str, Any]]:
        cache_key = f"{league_slug}_{days_window}"
        now = time.time()
        if cache_key in self._cache and (now - self._cache_time.get(cache_key, 0) < self.cache_ttl):
            return self._cache[cache_key]

        try:
            today = datetime.now(timezone.utc)
            start = (today - timedelta(days=days_window)).strftime('%Y%m%d')
            end = (today + timedelta(days=days_window)).strftime('%Y%m%d')
            url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league_slug}/scoreboard?dates={start}-{end}"
            
            # ESPN requires simple Mozilla/5.0 User-Agent
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode('utf-8'))

            events = []
            for ev in data.get('events', []):
                status_name = ev.get('status', {}).get('type', {}).get('name', '')
                status_detail = ev.get('status', {}).get('type', {}).get('shortDetail', '')
                competitions = ev.get('competitions', [{}])
                if not competitions:
                    continue
                competitors = competitions[0].get('competitors', [])
                home = next((c for c in competitors if c.get('homeAway') == 'home'), {})
                away = next((c for c in competitors if c.get('homeAway') == 'away'), {})
                
                h_name = home.get('team', {}).get('displayName', '')
                a_name = away.get('team', {}).get('displayName', '')
                h_score = home.get('score', '')
                a_score = away.get('score', '')

                events.append({
                    "home_name": h_name,
                    "away_name": a_name,
                    "home_score": h_score,
                    "away_score": a_score,
                    "status_name": status_name,
                    "status_detail": status_detail,
                    "is_final": status_name == "STATUS_FULL_TIME",
                    "in_progress": status_name in ["STATUS_IN_PROGRESS", "STATUS_HALFTIME", "STATUS_FIRST_HALF", "STATUS_SECOND_HALF"]
                })

            self._cache[cache_key] = events
            self._cache_time[cache_key] = now
            return events
        except Exception:
            return self._cache.get(cache_key, [])

    def resolve_match_results(self, match_titles: List[str], round_category: str = "PL") -> Dict[str, Dict[str, Any]]:
        league_slug = self.LEAGUES.get(round_category, "eng.1")
        events = self.fetch_league_events(league_slug=league_slug)
        
        if not events and league_slug != "eng.1":
            events = self.fetch_league_events(league_slug="eng.1")

        results: Dict[str, Dict[str, Any]] = {}

        for title in match_titles:
            if " vs " not in title:
                continue
            p1, p2 = title.split(" vs ", 1)
            w1 = self.clean_team_words(p1)
            w2 = self.clean_team_words(p2)

            matched_event = None
            for ev in events:
                eh = self.clean_team_words(ev["home_name"])
                ea = self.clean_team_words(ev["away_name"])
                if (w1 & eh) and (w2 & ea):
                    matched_event = ev
                    break

            if matched_event:
                h_score = matched_event["home_score"]
                a_score = matched_event["away_score"]
                is_final = matched_event["is_final"]
                in_progress = matched_event["in_progress"]

                actual = None
                score_str = ""
                if h_score is not None and a_score is not None and str(h_score) != "" and str(a_score) != "":
                    score_str = f"{h_score} - {a_score}"
                    try:
                        hs_int = int(h_score)
                        as_int = int(a_score)
                        if hs_int > as_int:
                            actual = "Home"
                        elif as_int > hs_int:
                            actual = "Away"
                        else:
                            actual = "Draw"
                    except ValueError:
                        actual = None

                status = "pending"
                if is_final:
                    status = "final"
                elif in_progress:
                    status = "in_progress"

                results[title] = {
                    "matched": True,
                    "status": status,
                    "is_final": is_final,
                    "in_progress": in_progress,
                    "score": score_str,
                    "actual": actual if (is_final or in_progress) else None,
                    "home_team": matched_event["home_name"],
                    "away_team": matched_event["away_name"]
                }
            else:
                results[title] = {
                    "matched": False,
                    "status": "unknown",
                    "is_final": False,
                    "in_progress": False,
                    "score": "",
                    "actual": None
                }

        return results
