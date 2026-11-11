"""
Krillion Leaderboard — a shared, public leaderboard for friends who play Krillion.

- Anyone with the link can VIEW the leaderboards (no login).
- Friends add themselves by name once and submit their OWN results.
- The app owner never has to type anyone's scores in.

Storage: SQLite (Python standard library only — no dependencies to install).
Run:  python3 main.py     (opens on $PORT, default 8000)
"""
import json
import os
import re
import sqlite3
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

BASE = Path(__file__).parent
DB_PATH = Path(os.environ.get("DB_PATH", "")) if os.environ.get("DB_PATH") else BASE / "data.db"
STATIC = BASE / "static"


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
            date TEXT NOT NULL,
            score INTEGER NOT NULL CHECK (score BETWEEN 0 AND 700),
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(player_id, date)
        );
        CREATE TABLE IF NOT EXISTS krillions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            result_id INTEGER NOT NULL REFERENCES results(id) ON DELETE CASCADE,
            question TEXT NOT NULL DEFAULT '',
            answer TEXT NOT NULL DEFAULT ''
        );
        """)


def get_or_create_player(c, name):
    name = " ".join(str(name).strip().split())[:40]
    if not name:
        raise ValueError("Name can't be empty")
    c.execute("INSERT OR IGNORE INTO players (name) VALUES (?)", (name,))
    row = c.execute("SELECT id, name FROM players WHERE name = ? COLLATE NOCASE",
                    (name,)).fetchone()
    return {"id": row["id"], "name": row["name"]}


def compute_state():
    with db() as c:
        players = [dict(r) for r in c.execute("SELECT id, name FROM players ORDER BY name")]
        results = []
        for r in c.execute("SELECT * FROM results ORDER BY date DESC, id DESC"):
            kr = [dict(k) for k in c.execute(
                "SELECT question, answer FROM krillions WHERE result_id = ?", (r["id"],))]
            results.append({"id": r["id"], "player_id": r["player_id"],
                            "date": r["date"], "score": r["score"], "krillions": kr})

    by_player = {p["id"]: [] for p in players}
    for r in results:
        by_player.setdefault(r["player_id"], []).append(r)

    stats = []
    for p in players:
        games = by_player.get(p["id"], [])
        if games:
            scores = [g["score"] for g in games]
            hi = max(games, key=lambda g: g["score"])
            lo = min(games, key=lambda g: g["score"])
            kr_list = [{"question": k["question"], "answer": k["answer"], "date": g["date"]}
                       for g in games for k in g["krillions"]]
            stats.append({
                "player_id": p["id"], "name": p["name"], "games": len(games),
                "highest": hi["score"], "highest_date": hi["date"],
                "lowest": lo["score"], "lowest_date": lo["date"],
                "average": round(sum(scores) / len(scores), 1),
                "krillion_count": len(kr_list), "krillions": kr_list,
            })
        else:
            stats.append({"player_id": p["id"], "name": p["name"], "games": 0,
                          "highest": None, "highest_date": None,
                          "lowest": None, "lowest_date": None,
                          "average": None, "krillion_count": 0, "krillions": []})

    played = [s for s in stats if s["games"] > 0]
    boards = {
        "highest_score": sorted(played, key=lambda s: (-s["highest"], s["name"])),
        "highest_average": sorted(played, key=lambda s: (-s["average"], s["name"])),
        "lowest_score": sorted(played, key=lambda s: (s["lowest"], s["name"])),
        "most_krillions": sorted(played, key=lambda s: (-s["krillion_count"], s["name"])),
    }
    return {"players": players, "results": results, "stats": stats, "boards": boards}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/state":
            return self._json(compute_state())
        if path in ("/", "/index.html"):
            return self._static("index.html", "text/html")
        m = re.fullmatch(r"/static/([\w.\-]+)", path)
        if m:
            ctype = ("text/css" if m.group(1).endswith(".css")
                     else "application/javascript" if m.group(1).endswith(".js")
                     else "text/plain")
            return self._static(m.group(1), ctype)
        return self._json({"error": "not found"}, 404)

    def _static(self, name, ctype):
        f = STATIC / name
        if not f.exists():
            return self._json({"error": "not found"}, 404)
        body = f.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            data = self._read_json()
            if path == "/api/players":
                with db() as c:
                    player = get_or_create_player(c, data.get("name", ""))
                return self._json({"player": player}, 201)

            if path == "/api/results":
                name = data.get("player_name", "")
                rdate = str(data.get("date") or date.today().isoformat())
                date.fromisoformat(rdate)  # validates YYYY-MM-DD
                score = int(data.get("score"))
                if not 0 <= score <= 700:
                    raise ValueError("Score must be between 0 and 700")
                krillions = data.get("krillions") or []
                if len(krillions) > 7:
                    raise ValueError("At most 7 One in a Krillion answers per game")
                with db() as c:
                    player = get_or_create_player(c, name)
                    c.execute(
                        "INSERT INTO results (player_id, date, score) VALUES (?, ?, ?) "
                        "ON CONFLICT(player_id, date) DO UPDATE SET score = excluded.score",
                        (player["id"], rdate, score))
                    rid = c.execute("SELECT id FROM results WHERE player_id = ? AND date = ?",
                                    (player["id"], rdate)).fetchone()["id"]
                    c.execute("DELETE FROM krillions WHERE result_id = ?", (rid,))
                    for k in krillions:
                        q = str(k.get("question", "")).strip()[:300]
                        a = str(k.get("answer", "")).strip()[:120]
                        c.execute("INSERT INTO krillions (result_id, question, answer) "
                                  "VALUES (?, ?, ?)", (rid, q, a))
                return self._json({"ok": True, "player": player, "date": rdate,
                                   "score": score}, 201)
            return self._json({"error": "not found"}, 404)
        except (ValueError, TypeError, KeyError) as e:
            return self._json({"error": str(e)}, 400)
        except json.JSONDecodeError:
            return self._json({"error": "invalid JSON"}, 400)

    def do_DELETE(self):
        m = re.fullmatch(r"/api/results/(\d+)", urlparse(self.path).path)
        if not m:
            return self._json({"error": "not found"}, 404)
        with db() as c:
            c.execute("DELETE FROM results WHERE id = ?", (int(m.group(1)),))
        return self._json({"ok": True})


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", "8000"))
    print(f"Krillion Leaderboard running on port {port}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
