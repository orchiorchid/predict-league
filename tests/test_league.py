"""Offline tests against a real snapshot of the organizer's sheet (15 Sep 2026)."""
import copy
import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.league import build_league, describe_tag, parse_result
from backend.live import team_tokens, _similarity, outcome_from_scores
from backend.service import LeagueService
from backend.sheet import parse_form_grid

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sheet_2026-09-15.xlsx")
MATCH_COLS = list("CDEFGHIJKL")
KEY_COLS = list("PQRSTUVWXY")
RESULT_COLS = ["AA", "AB", "AC", "AD", "AE", "AF", "AG", "AH", "AI", "AJ", "AK"]


@pytest.fixture(scope="module")
def xlsx_bytes():
    with open(FIXTURE, "rb") as f:
        return f.read()


@pytest.fixture()
def grid(xlsx_bytes):
    return parse_form_grid(xlsx_bytes)


def no_live(*_):
    return [None] * 10


def by_id(league, rid):
    return next(r for r in league["rounds"] if r["id"] == rid)


def player(league, key):
    return next(p for p in league["players"] if p["key"] == key)


def r6_as_open_round(grid, keep_points=False, drop_later_rows=True):
    """Rewind the sheet to before the organizer published Round 6 (PL MD4)."""
    g = copy.deepcopy(grid)
    results = [parse_result(g[213][c]) for c in RESULT_COLS[1:]]
    for r in (213, 214, 215, 216):
        for c in RESULT_COLS:
            g[r].pop(c, None)
    if not keep_points:
        for r in range(213, 246):
            g.get(r, {}).pop("O", None)
    if drop_later_rows:
        for r in [r for r in g if r >= 246]:
            del g[r]
        for col, res in zip(MATCH_COLS, results):
            g[1][col] = f"PL MD4 [{res['home']} vs {res['away']}]"
        r5 = [parse_result(g[175][c])["outcome"] for c in RESULT_COLS[1:]]
        for col, outcome in zip(KEY_COLS, r5):
            g[1][col] = outcome  # stale answer key left over from Round 5
    return g, results


# ---------------------------------------------------------------- parsing helpers

def test_parse_result_handles_penalties():
    res = parse_result("Stoke 1 (4) - 1 (5) Hull")
    assert (res["home"], res["away"], res["outcome"]) == ("Stoke", "Hull", "Away")
    assert parse_result("Aston Villa 1 - 2 Nott'm Forest")["outcome"] == "Away"
    assert parse_result("postponed")["outcome"] is None


def test_describe_tag():
    assert describe_tag("PL MD4")["stage"] == "Matchday 4"
    assert describe_tag("LC R3")["competition"] == "League Cup"
    assert describe_tag("UCL MD1")["category"] == "europe"


def test_team_matching_distinguishes_manchester_clubs():
    utd = team_tokens("Man Utd")
    assert _similarity(utd, team_tokens("Manchester United")) == 1
    assert _similarity(utd, team_tokens("Manchester City")) < 1
    assert _similarity(team_tokens("Nott'm Forest"), team_tokens("Nottingham Forest")) == 1
    assert _similarity(team_tokens("Bodø/Glimt"), team_tokens("Bodo/Glimt")) == 1


def test_shootout_winner_takes_the_tie():
    assert outcome_from_scores(1, 1, 4, 5) == "Away"
    assert outcome_from_scores(1, 1) == "Draw"


# ---------------------------------------------------------------- the sheet as it is today

def test_current_sheet_rounds(grid):
    league = build_league(grid, live=no_live)
    tags = [r["tag"] for r in league["rounds"]]
    assert tags == ["PL MD1", "LC R2", "PL MD2", "PL MD3", "UCL MD1", "PL MD4", "LC R3"]
    assert [r["status"] for r in league["rounds"][:6]] == ["final"] * 6
    assert league["current_round"] == "r7"

    r6, r7 = by_id(league, "r6"), by_id(league, "r7")
    assert r6["entries"] == 33 and r6["matches"][0]["title"] == "Aston Villa vs Nott'm Forest"
    assert r7["status"] == "upcoming" and r7["entries"] == 26
    assert r7["matches"][0]["title"] == "Peterborough vs Barnsley"
    assert league["warnings"] == []


def test_sheet_points_match_published_results(grid):
    league = build_league(grid, live=no_live)
    assert player(league, "qqq666")["total"] == 14
    assert player(league, "qqq666")["rounds"] == {"r4": 4, "r5": 10}
    sock = player(league, "sockodile")
    assert sock["total"] == 31 and set(sock["aliases"]) == {"sockodile", "Sockodile"}
    assert player(league, "mchto")["rounds"]["r6"] == 6
    # "U/gopher246" in the form is the same person as "gopher246"
    assert set(player(league, "gopher246")["rounds"]) == {"r1", "r7"}
    # the organizer's corrected name (column N) wins over the typo in column B
    assert all(p["key"] != "rithvikkstar123" for p in league["players"])


def test_upcoming_round_does_not_count_as_zero(grid):
    league = build_league(grid, live=no_live)
    f4lcon = player(league, "f4lcon")
    assert f4lcon["rounds"]["r7"] is None
    assert f4lcon["total"] == 31


def test_ranks_are_shared_on_ties(grid):
    league = build_league(grid, live=no_live)
    top = [p for p in league["players"] if p["total"] == 31]
    assert len(top) >= 2 and all(p["rank"] == 1 for p in top)
    next_rank = next(p["rank"] for p in league["players"] if p["total"] < 31)
    assert next_rank == len(top) + 1


# ---------------------------------------------------------------- transition periods

def fake_live_from(results, statuses=None):
    kickoff = datetime(2026, 9, 12, 14, tzinfo=timezone.utc)

    def resolve(code, matches, since):
        assert code == "PL"
        out = []
        for i, res in enumerate(results):
            status = (statuses or {}).get(i, "final")
            live = status in ("final", "live")
            out.append({"status": status, "score": res["score"] if live else None,
                        "outcome": res["outcome"] if live else None, "detail": "FT" if status == "final" else "55'",
                        "kickoff": kickoff + timedelta(hours=i)})
        return out
    return resolve


def test_round_finished_but_not_published_uses_live_results(grid):
    """The organizer's complaint: after the last match everyone's score was still pending."""
    original = build_league(grid, live=no_live)
    rewound, results = r6_as_open_round(grid)
    league = build_league(rewound, live=fake_live_from(results))

    r6 = by_id(league, "r6")
    assert league["current_round"] == "r6"
    assert r6["status"] == "completed" and not r6["official"]
    assert len(league["rounds"]) == 6
    for p in original["players"]:
        if "r6" in p["rounds"]:
            assert player(league, p["key"])["rounds"]["r6"] == p["rounds"]["r6"], p["name"]
            assert player(league, p["key"])["total"] == p["total"]


def test_round_in_progress_shows_live_points(grid):
    rewound, results = r6_as_open_round(grid)
    statuses = {i: "scheduled" for i in range(6, 10)}
    statuses[5] = "live"
    league = build_league(rewound, live=fake_live_from(results, statuses))
    r6 = by_id(league, "r6")
    assert r6["status"] == "live"
    mchto = player(league, "mchto")
    assert mchto["rounds"]["r6"] <= 6
    assert mchto["live"] in (0, 1)
    assert r6["matches"][9]["correct_pct"] is None


def test_stale_answer_key_is_ignored(grid):
    rewound, results = r6_as_open_round(grid, keep_points=True)
    league = build_league(rewound, live=no_live)
    r6 = by_id(league, "r6")
    assert r6["status"] == "upcoming"
    assert all(m["outcome"] is None for m in r6["matches"])


def test_answer_key_of_previous_round_does_not_leak_into_new_form(grid):
    rewound, _ = r6_as_open_round(grid, keep_points=True, drop_later_rows=False)
    league = build_league(rewound, live=no_live)  # row 1 key still holds Round 6 results
    r7 = by_id(league, "r7")
    assert r7["status"] == "upcoming"
    assert all(m["outcome"] is None for m in r7["matches"])


def test_organizer_answer_key_confirms_results_without_espn(grid):
    rewound, results = r6_as_open_round(grid, keep_points=True)
    for col, res in zip(KEY_COLS, results):
        rewound[1][col] = res["outcome"]
    league = build_league(rewound, live=no_live)
    r6 = by_id(league, "r6")
    assert r6["status"] == "completed"
    assert all(m["confirmed"] for m in r6["matches"])
    assert player(league, "mchto")["rounds"]["r6"] == 6


def test_new_form_opened_before_results_row_was_written(grid):
    rewound, _ = r6_as_open_round(grid, keep_points=True, drop_later_rows=False)
    league = build_league(rewound, live=no_live)
    assert [r["status"] for r in league["rounds"]] == ["final"] * 5 + ["awaiting", "upcoming"]
    r6, r7 = by_id(league, "r6"), by_id(league, "r7")
    assert r6["entries"] == 33 and r7["entries"] == 26
    assert player(league, "mchto")["rounds"]["r6"] == 6  # organizer's points column still counts
    assert league["current_round"] == "r7"


def test_unscored_finished_round_is_split_by_submission_gap(grid):
    rewound, _ = r6_as_open_round(grid, keep_points=False, drop_later_rows=False)
    league = build_league(rewound, live=no_live)
    r6 = by_id(league, "r6")
    assert r6["status"] == "awaiting" and r6["entries"] == 33
    assert player(league, "mchto")["rounds"]["r6"] is None
    assert by_id(league, "r7")["entries"] == 26


def test_snapshot_restores_titles_of_unpublished_round(grid):
    rewound, results = r6_as_open_round(grid)
    first = build_league(rewound, live=fake_live_from(results))
    key, snap = first["snapshot"]

    later, _ = r6_as_open_round(grid, keep_points=False, drop_later_rows=False)
    league = build_league(later, live=no_live, snapshots={key: snap})
    r6 = by_id(league, "r6")
    assert r6["tag"] == "PL MD4" and r6["matches"][0]["title"] == "Aston Villa vs Nott'm Forest"
    assert player(league, "mchto")["rounds"]["r6"] == 6


# ---------------------------------------------------------------- API

class FakeLive:
    def resolve(self, code, matches, since):
        return [None] * len(matches)


@pytest.fixture()
def client(xlsx_bytes, monkeypatch):
    from backend import main

    svc = LeagueService(downloader=lambda _id: xlsx_bytes, live=FakeLive())
    monkeypatch.setattr(main, "service", svc)
    return TestClient(main.app)


def test_api_league(client):
    res = client.get("/api/league")
    assert res.status_code == 200
    data = res.json()
    assert data["current_round"] == "r7"
    assert len(data["rounds"]) == 7
    assert data["meta"]["stale"] is False
    assert data["picks"]["r7"]["mchto"] == "AHAHAAAAAH"


def test_api_player(client):
    res = client.get("/api/players/Qqq666")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 14
    r5 = next(r for r in body["round_details"] if r["id"] == "r5")
    assert all(p["correct"] for p in r5["picks"])
    assert client.get("/api/players/nobody-at-all").status_code == 404


def test_api_serves_frontend(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "Prediction League" in res.text


def test_service_keeps_last_good_data_when_google_fails(xlsx_bytes):
    calls = {"n": 0}

    def flaky(_id):
        calls["n"] += 1
        if calls["n"] > 1:
            raise RuntimeError("Google is down")
        return xlsx_bytes

    svc = LeagueService(downloader=flaky, live=FakeLive(), min_force_interval=0)
    assert svc.get()["current_round"] == "r7"
    data = svc.get(force=True)
    assert data["current_round"] == "r7"
    assert data["meta"]["stale"] is True and "Google is down" in data["meta"]["error"]
