# 🏆 Prediction League — Google Sheets Results & Standings Service

A real-time service for fetching data, calculating points, and displaying tournament standings and participant predictions from a Google Spreadsheet:
`https://docs.google.com/spreadsheets/d/1oibdWWMrTXoFXozDIo4jfcukfNNJOfMbrTduzDS0Ji4/edit?gid=304172133`

---

## 🌟 Key Features

1. **Direct Google Sheets Live Synchronization**:
   - Queries Google Sheets directly to parse live responses, round scores, and overall standings.
   - Automatically computes points on the fly for rows 174+ (where the spreadsheet author hasn't dragged formulas down yet) by matching predictions against the master match outcomes in row 0.
   - Built-in 15-second cache to prevent Google rate-limits, with a **"Refresh"** button (`fresh=true`) to force instant re-fetching anytime.
2. **Case-Insensitive Username Aggregation**:
   - Automatically merges variations in username casing (e.g. `qqq666` and `Qqq666`, `sockodile` and `Sockodile`, `kopite33` and `Kopite33`) into a single unified participant profile with combined points and predictions across all rounds.
3. **Personal Results & Search**:
   - Fast autocomplete search by username or alias.
   - Detailed profile modal: overall rank (with 🥇, 🥈, 🥉 badges), total tournament points, and points breakdown across Round 1, Round 2, Round 3, Round 4, and Round 5.
   - Full 10-match prediction breakdown for current round with visual indicators for correct (+1 pt) and incorrect (0 pts) predictions.
   - Direct shareable URLs (e.g. `http://localhost:8000/?user=sockodile`).
4. **Interactive Leaderboard**:
   - Tab navigation: "Overall Standings", "Round 5 (UCL MD1)", "Round 4", "Round 3", "Round 2", "Round 1".
   - In-table instant search/filtering by nickname.
   - Clicking any participant row immediately opens their full profile.
5. **Community Match Statistics**:
   - Segmented distribution bars showing the percentage of participants voting for Home Win (1), Draw (X), or Away Win (2) for each match.

---

## 🚀 Quick Start

### Option 1: Run with Python Locally

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the application
python run.py
```

Open your browser:
- Web App: [http://localhost:8000](http://localhost:8000)
- Swagger API Docs: [http://localhost:8000/docs](http://localhost:8000/docs)

### Option 2: Run with Docker Compose

```bash
docker-compose up --build
```

---

## 🌐 Deploy to Cloud (Render, Railway, Fly.io, VPS)

For a complete step-by-step guide on how to deploy this project for free or on a server, see:
👉 **[DEPLOYMENT.md](DEPLOYMENT.md)**

---

## 📡 REST API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/data` | Returns complete tournament data. Add `?fresh=true` to force re-fetch from Google Sheets. |
| `GET` | `/api/user/{username}` | Returns participant profile, round breakdown, and match predictions (case-insensitive). |
| `GET` | `/api/search?q={query}` | Fast autocomplete search for usernames and aliases. |
| `GET` | `/api/matches` | Current round match voting distribution statistics. |
| `GET` | `/api/rounds/{round_id}` | Leaderboard for a specific round (`r1`, `r2`, `r3`, `r4`, `r5`). |
| `POST` | `/api/refresh` | Forces cache invalidation and immediate re-fetch from Google Sheets. |

---

## 🧪 Testing

Run the automated test suite:
```bash
python tests/test_service.py
```
Validates Google Sheets connectivity, case-insensitive merging (`qqq666` & `Qqq666`), scoring accuracy, and all REST API routes.
