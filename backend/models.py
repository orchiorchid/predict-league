from typing import List, Dict, Optional, Any
from pydantic import BaseModel

class MatchPrediction(BaseModel):
    match: str
    prediction: str
    actual: Optional[str] = None
    correct: Optional[bool] = None
    points: int = 0

class RoundScore(BaseModel):
    round_id: str
    round_name: str
    score: Optional[float] = None
    participated: bool = False

class UserDetail(BaseModel):
    username: str
    aliases: List[str] = []
    rank: int
    total_score: float
    base_score: float
    r5_score: float
    round_scores: List[RoundScore]
    r5_predictions: List[MatchPrediction] = []

class LeaderboardUser(BaseModel):
    rank: int
    username: str
    aliases: List[str] = []
    total_score: float
    round_scores: Dict[str, Optional[float]] = {}
    r5_score: float = 0.0

class MatchDistribution(BaseModel):
    match: str
    actual: Optional[str] = None
    home: int = 0
    draw: int = 0
    away: int = 0
    total: int = 0
    home_pct: float = 0.0
    draw_pct: float = 0.0
    away_pct: float = 0.0

class RoundLeaderboard(BaseModel):
    id: str
    name: str
    standings: List[Dict[str, Any]]

class FullDataResponse(BaseModel):
    spreadsheet_id: str
    spreadsheet_url: str
    last_updated: str
    cached: bool
    total_participants: int
    rounds: List[Dict[str, str]]
    leaderboard: List[LeaderboardUser]
    match_distributions: List[MatchDistribution]
