import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Test runner for services and API endpoints
from fastapi.testclient import TestClient
from backend.main import app
from backend.sheet_service import SheetService

client = TestClient(app)

def test_sheet_service_fetch():
    service = SheetService()
    data = service.get_data(force=True)
    assert data is not None
    assert "leaderboard" in data
    assert len(data["leaderboard"]) > 100
    assert "rounds" in data
    assert len(data["rounds"]) >= 6
    assert "match_distributions" in data
    assert len(data["match_distributions"]) == 10
    assert "round_match_distributions" in data
    assert "r5" in data["round_match_distributions"]
    assert "r6" in data["round_match_distributions"]

def test_case_insensitive_merging_qqq666():
    service = SheetService()
    
    # 1. Lookup by lowercase
    u_lower = service.get_user_detail("qqq666")
    assert u_lower is not None
    
    # 2. Lookup by uppercase
    u_upper = service.get_user_detail("Qqq666")
    assert u_upper is not None
    
    # Both must resolve to the same merged participant
    assert u_lower["username"] == u_upper["username"]
    assert u_lower["total_score"] == 14.0
    assert u_upper["total_score"] == 14.0
    assert "Qqq666" in u_lower["aliases"]
    assert "qqq666" in u_lower["aliases"]

    # Check round scores: Round 4 had 4.0, Round 5 had 10.0 (10/10 correct)
    scores = {r["round_id"]: r["score"] for r in u_lower["round_scores"]}
    assert scores["r4"] == 4.0
    assert scores["r5"] == 10.0
    assert len(u_lower["r5_predictions"]) == 10
    assert all(p["correct"] is True for p in u_lower["r5_predictions"])
    assert all(p["points"] == 1 for p in u_lower["r5_predictions"])
    assert u_lower["r5_predictions"][0]["match"] == "Club Brugge vs Aston Villa"

    # Verify only ONE entry exists in leaderboard
    data = service.get_data()
    qqq_entries = [u for u in data["leaderboard"] if u["username"].lower() == "qqq666"]
    assert len(qqq_entries) == 1, f"Expected exactly 1 merged entry, found {len(qqq_entries)}"
    assert qqq_entries[0]["total_score"] == 14.0

def test_round_5_matches_preservation():
    service = SheetService()
    data = service.get_data()
    r5_matches = [m["match"] for m in data["round_match_distributions"]["r5"]]
    assert "Club Brugge vs Aston Villa" in r5_matches
    assert "Dortmund vs Villarreal" in r5_matches
    # Must NOT have Round 6 matches
    assert "Aston Villa vs Nott'm Forest" not in r5_matches

def test_round_6_active_predictions():
    service = SheetService()
    data = service.get_data()
    r6_matches = [m["match"] for m in data["round_match_distributions"]["r6"]]
    assert any("Aston Villa" in m or "Bournemouth" in m for m in r6_matches)
    assert len(data["round_predictions"]["r6"]) >= 30

def test_case_insensitive_merging_sockodile():
    service = SheetService()
    data = service.get_data()
    sock_entries = [u for u in data["leaderboard"] if u["username"].lower() == "sockodile"]
    assert len(sock_entries) == 1
    # Round 3 had 4.0 under 'Sockodile' and other rounds under 'sockodile'
    assert sock_entries[0]["total_score"] >= 24.0

def test_sheet_service_user_detail():
    service = SheetService()
    # Test user with R5 predictions
    user_detail = service.get_user_detail("WaifuWarrior18")
    assert user_detail is not None
    assert user_detail["username"].lower() == "waifuwarrior18".lower()
    assert user_detail["rank"] > 0
    assert user_detail["total_score"] > 0
    assert len(user_detail["r5_predictions"]) == 10

    # Test user without R5 predictions
    user_detail_legacy = service.get_user_detail("MadeMIGMIG")
    assert user_detail_legacy is not None
    assert user_detail_legacy["rank"] > 0
    assert user_detail_legacy["total_score"] >= 20.0

def test_sheet_service_search():
    service = SheetService()
    results = service.search_users("qqq")
    assert len(results) > 0
    assert any("qqq" in r["username"].lower() for r in results)

def test_api_endpoints():
    # Test /api/data
    res = client.get("/api/data")
    assert res.status_code == 200
    data = res.json()
    assert "leaderboard" in data
    assert "match_distributions" in data
    assert "round_match_distributions" in data

    # Test /api/search
    res = client.get("/api/search?q=qqq")
    assert res.status_code == 200
    search_data = res.json()
    assert len(search_data["results"]) == 1
    assert search_data["results"][0]["total_score"] == 14.0

    # Test /api/user/{username} for both casings
    res1 = client.get("/api/user/qqq666")
    res2 = client.get("/api/user/Qqq666")
    assert res1.status_code == 200
    assert res2.status_code == 200
    assert res1.json()["total_score"] == 14.0
    assert res2.json()["total_score"] == 14.0
    assert len(res1.json()["round_predictions"]["r5"]) == 10

    # Test /api/matches
    res = client.get("/api/matches")
    assert res.status_code == 200
    matches_data = res.json()
    assert len(matches_data["matches"]) == 10

    # Test /api/rounds/r5
    res = client.get("/api/rounds/r5")
    assert res.status_code == 200
    r5_data = res.json()
    assert len(r5_data["standings"]) > 0

    # Test /api/rounds/r6
    res = client.get("/api/rounds/r6")
    assert res.status_code == 200
    r6_data = res.json()
    assert len(r6_data["standings"]) > 0

    # Test /api/refresh
    res = client.post("/api/refresh")
    assert res.status_code == 200
    refresh_data = res.json()
    assert refresh_data["status"] == "success"

    # Test root HTML serving
    res = client.get("/")
    assert res.status_code == 200
    assert "Prediction League" in res.text
    assert "user-modal" in res.text

if __name__ == "__main__":
    print("Running test suite...")
    test_sheet_service_fetch()
    print("[OK] test_sheet_service_fetch passed")
    test_case_insensitive_merging_qqq666()
    print("[OK] test_case_insensitive_merging_qqq666 passed (qqq666 & Qqq666 merged into 14.0 pts, 10/10 correct in R5)")
    test_round_5_matches_preservation()
    print("[OK] test_round_5_matches_preservation passed (R5 has UCL MD1 matches preserved)")
    test_round_6_active_predictions()
    print("[OK] test_round_6_active_predictions passed (R6 has PL MD4 matches and live submissions)")
    test_case_insensitive_merging_sockodile()
    print("[OK] test_case_insensitive_merging_sockodile passed")
    test_sheet_service_user_detail()
    print("[OK] test_sheet_service_user_detail passed")
    test_sheet_service_search()
    print("[OK] test_sheet_service_search passed")
    test_api_endpoints()
    print("[OK] test_api_endpoints passed")
    print("\nALL TESTS PASSED SUCCESSFULLY!")
