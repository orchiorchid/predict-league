# ⚽ Prediction League

A website for the Reddit football prediction league. It reads the organizer's
[Google Sheet](https://docs.google.com/spreadsheets/d/1oibdWWMrTXoFXozDIo4jfcukfNNJOfMbrTduzDS0Ji4/edit?gid=304172133)
and shows standings, every round's fixtures and picks, and live scores for the round in play.

- **Standings**: shared ranks, movement since the last round, points per round, accuracy.
- **Current round**: kick-off countdown, live scores (ESPN), provisional points while matches are played.
- **Rounds**: fixtures with results, how the league picked (1 / X / 2), round table with everyone's picks.
- **Player profile**: points chart against the round average, all picks with how many others made the same call.
- **"This is me"**: pin your name once and it is highlighted everywhere (stored in your browser only).
- Shareable links: `/?player=sockodile`, `/?round=r6`.

## Run it

```bash
pip install -r requirements.txt
python run.py            # http://localhost:8000, API docs at /docs
```

or `docker compose up --build`. Deployment options are in [DEPLOYMENT.md](DEPLOYMENT.md).

## How the sheet is read

Nothing about rounds is hardcoded. Everything comes from the **Form Responses 1** tab:

| Where | What the site uses it for |
|---|---|
| Row 1, C–L | The open form's matches, e.g. `LC R3 [Peterborough vs Barnsley]`. The tag before `[` names the competition and stage. |
| Row 1, P–Y | Answer key. Used only for the round in play, and only once that round's rows have points in column O. |
| A, B, C–L | Timestamp, username, picks. |
| N, O | Username as corrected by the organizer (preferred over B) and round points. |
| AA, AB–AK on the **first row of a round** | Tag and results (`Aston Villa 1 - 2 Nott'm Forest`, penalties as `1 (4) - 1 (5)`). A round with this row is **Final**. |

Rounds after the last results row are handled like this:

1. Submissions are split into rounds where there is a pause of 30+ hours between two entries,
   or where scored rows are followed by unscored ones.
2. If the form header shows a new tag, the last group is the **round in play**. Its results come
   from ESPN (League Cup, FA Cup, Premier League, UEFA competitions). Points are provisional
   until the organizer writes the results row.
3. A finished round whose results row is missing is shown as **Awaiting results**. It uses the
   organizer's points from column O and the fixture names the site saved while the round was open.

If the sheet and the results row ever disagree, column O wins, so manual corrections are respected.
Usernames are merged case-insensitively, and a leading `u/` is ignored.

## API

| Endpoint | |
|---|---|
| `GET /api/league` | Rounds (matches, results, pick distribution), players (totals, per-round points, rank, movement), compact picks |
| `GET /api/players/{name}` | One player with every pick and whether it was right |
| `POST /api/refresh` | Re-read the sheet now (at most once per 20 s) |
| `GET /api/health` | Liveness check |

Responses are cached for 60 s. When Google or ESPN fails, the last good data is served with `meta.stale = true`.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The tests run offline against a saved copy of the sheet (`tests/fixtures`). They also rewind it to
simulate the transition periods: a round finished but not yet published, a new form opened before
results were written, and the answer key still holding the previous round.
