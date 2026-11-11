"""
WSGI entry point for PythonAnywhere (and any other WSGI host).

PythonAnywhere free web apps don't run `python3 main.py` directly — they
load a WSGI file. This file reuses the exact same database logic from
main.py (players, results, krillions, compute_state), so the app behaves
identically, just served through WSGI instead of the built-in HTTP server.

On PythonAnywhere, point your web app's WSGI configuration file at this
file (or paste its contents into the WSGI file PythonAnywhere gives you),
with the project files in the same directory.
"""
import json
import re
from datetime import date
from urllib.parse import parse_qs

import main

main.init_db()

STATIC_TYPES = {
    ".html": "text/html",
    ".css": "text/css",
    ".js": "application/javascript",
}


def _response(start_response, status, body, ctype="application/json"):
    if isinstance(body, (dict, list)):
        body = json.dumps(body).encode()
        ctype = "application/json"
    elif isinstance(body, str):
        body = body.encode()
    start_response(status, [
        ("Content-Type", ctype + "; charset=utf-8" if ctype.startswith("text/") else ctype),
        ("Content-Length", str(len(body))),
    ])
    return [body]


def application(environ, start_response):
    method = environ.get("REQUEST_METHOD", "GET")
    path = environ.get("PATH_INFO", "/") or "/"

    try:
        if method == "GET" and path == "/api/state":
            return _response(start_response, "200 OK", main.compute_state())

        if method == "GET" and path in ("/", "/index.html"):
            return _response(start_response, "200 OK",
                             (main.STATIC / "index.html").read_bytes(), "text/html")

        m = re.fullmatch(r"/static/([\w.\-]+)", path)
        if method == "GET" and m:
            name = m.group(1)
            suffix = "." + name.rsplit(".", 1)[-1] if "." in name else ""
            f = main.STATIC / name
            if f.exists():
                return _response(start_response, "200 OK", f.read_bytes(),
                                 STATIC_TYPES.get(suffix, "text/plain"))
            return _response(start_response, "404 Not Found", {"error": "not found"})

        if method in ("POST", "DELETE"):
            length = int(environ.get("CONTENT_LENGTH") or 0)
            raw = environ["wsgi.input"].read(length) if length else b"{}"
            data = json.loads(raw or b"{}")

            if method == "POST" and path == "/api/players":
                with main.db() as c:
                    player = main.get_or_create_player(c, data.get("name", ""))
                return _response(start_response, "201 Created", {"player": player})

            if method == "POST" and path == "/api/results":
                name = data.get("player_name", "")
                rdate = str(data.get("date") or date.today().isoformat())
                date.fromisoformat(rdate)
                score = int(data.get("score"))
                if not 0 <= score <= 700:
                    raise ValueError("Score must be between 0 and 700")
                krillions = data.get("krillions") or []
                if len(krillions) > 7:
                    raise ValueError("At most 7 One in a Krillion answers per game")
                with main.db() as c:
                    player = main.get_or_create_player(c, name)
                    c.execute(
                        "INSERT INTO results (player_id, date, score) VALUES (?, ?, ?) "
                        "ON CONFLICT(player_id, date) DO UPDATE SET score = excluded.score",
                        (player["id"], rdate, score))
                    rid = c.execute(
                        "SELECT id FROM results WHERE player_id = ? AND date = ?",
                        (player["id"], rdate)).fetchone()["id"]
                    c.execute("DELETE FROM krillions WHERE result_id = ?", (rid,))
                    for k in krillions:
                        q = str(k.get("question", "")).strip()[:300]
                        a = str(k.get("answer", "")).strip()[:120]
                        c.execute("INSERT INTO krillions (result_id, question, answer) "
                                  "VALUES (?, ?, ?)", (rid, q, a))
                return _response(start_response, "201 Created",
                                 {"ok": True, "player": player, "date": rdate, "score": score})

            m2 = re.fullmatch(r"/api/results/(\d+)", path)
            if method == "DELETE" and m2:
                with main.db() as c:
                    c.execute("DELETE FROM results WHERE id = ?", (int(m2.group(1)),))
                return _response(start_response, "200 OK", {"ok": True})

        return _response(start_response, "404 Not Found", {"error": "not found"})
    except (ValueError, TypeError, KeyError) as e:
        return _response(start_response, "400 Bad Request", {"error": str(e)})
    except json.JSONDecodeError:
        return _response(start_response, "400 Bad Request", {"error": "invalid JSON"})
