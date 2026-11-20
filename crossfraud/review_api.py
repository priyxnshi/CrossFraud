"""Loopback-only JSON API for reviewing the supplied synthetic alerts."""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import sqlite3
from urllib.parse import parse_qs, urlsplit

from crossfraud.review_catalog import DemoCatalog

OUTCOMES = {"confirmed", "dismissed", "unresolved"}


class ReviewStore:
    def __init__(self, data_dir, database):
        reports = Path(data_dir) / "reports"
        evaluation = json.loads((reports / "phase3_evaluation.json").read_text(encoding="utf-8"))
        if evaluation.get("source") != "synthetic":
            raise ValueError("Demo requires a synthetic evaluation")
        examples = json.loads((reports / "phase3_alert_examples.json").read_text(encoding="utf-8"))
        if not isinstance(examples, list) or any(alert.get("schema_version") != "phase3-alert-v1" for alert in examples):
            raise ValueError("Unsupported synthetic alert schema")
        self.catalog = DemoCatalog(data_dir)
        self.alerts = {hashlib.sha256(json.dumps(alert, sort_keys=True).encode()).hexdigest()[:20]: alert
                       for alert in examples}
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("""CREATE TABLE IF NOT EXISTS review_history (
                id INTEGER PRIMARY KEY, alert_id TEXT NOT NULL,
                outcome TEXT NOT NULL CHECK (outcome IN ('confirmed', 'dismissed', 'unresolved')),
                recorded_at_utc TEXT NOT NULL
            )""")

    def notes(self, alert_id):
        with closing(sqlite3.connect(self.database)) as db:
            db.execute("CREATE TABLE IF NOT EXISTS review_notes (id INTEGER PRIMARY KEY, alert_id TEXT NOT NULL, note TEXT NOT NULL, recorded_at_utc TEXT NOT NULL)")
            rows = db.execute("SELECT note, recorded_at_utc FROM review_notes WHERE alert_id = ? ORDER BY id", (alert_id,)).fetchall()
        return [{"note": note, "recorded_at_utc": stamp} for note, stamp in rows]

    def add_note(self, alert_id, note):
        if not isinstance(note, str) or not 1 <= len(note.strip()) <= 1000:
            raise ValueError("Enter a note of 1-1000 characters.")
        self.notes(alert_id)
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("INSERT INTO review_notes (alert_id,note,recorded_at_utc) VALUES (?,?,?)",
                       (alert_id, note.strip(), datetime.now(timezone.utc).isoformat()))
        return self.notes(alert_id)

    def get(self, alert_id):
        alert = self.alerts[alert_id]
        with closing(sqlite3.connect(self.database)) as db:
            history = db.execute("SELECT outcome, recorded_at_utc FROM review_history WHERE alert_id = ? ORDER BY id",
                                 (alert_id,)).fetchall()
        return {"alert_id": alert_id, **alert, "review_outcome": history[-1][0] if history else "unresolved",
                "review_history": [{"outcome": outcome, "recorded_at_utc": stamp} for outcome, stamp in history]}

    def set_outcome(self, alert_id, outcome):
        if alert_id not in self.alerts:
            raise KeyError(alert_id)
        if not isinstance(outcome, str) or outcome not in OUTCOMES:
            raise ValueError("Use confirmed, dismissed, or unresolved")
        timestamp = datetime.now(timezone.utc).isoformat()
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("INSERT INTO review_history (alert_id, outcome, recorded_at_utc) VALUES (?, ?, ?)",
                       (alert_id, outcome, timestamp))
        return self.get(alert_id)


class ReviewHandler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *args):
        return

    def respond(self, status, value):
        payload = json.dumps(value, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def allowed(self):
        allowed_hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        host = self.headers.get("Host")
        origin = self.headers.get("Origin")
        if host in allowed_hosts and (origin is None or origin == f"http://{host}"):
            return True
        self.respond(403, {"error": "Use the loopback URL shown by the server"})
        return False

    def do_GET(self):
        if not self.allowed():
            return
        parsed = urlsplit(self.path)
        path = parsed.path
        store = self.server.store
        assets = {"/": ("index.html", "text/html"), "/ui.css": ("ui.css", "text/css"),
                  "/ui.js": ("ui.js", "text/javascript")}
        if path in assets:
            filename, media_type = assets[path]
            body = (Path(__file__).with_name("review_web") / filename).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", f"{media_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/catalog":
            return self.respond(200, store.catalog.index())
        if path.startswith("/conversations/"):
            entity = path.removeprefix("/conversations/")
            cutoff = parse_qs(parsed.query).get("cutoff", [None])[0]
            detail = store.catalog.conversation(entity, cutoff)
            return self.respond(200, detail) if detail else self.respond(404, {"error": "Conversation unavailable"})
        if path.startswith("/alerts/") and path.endswith("/notes"):
            key = path.split("/")[2]
            return self.respond(200, store.notes(key)) if key in store.alerts else self.respond(404, {"error": "Alert not found"})
        if path == "/alerts":
            return self.respond(200, {"source": "synthetic", "review_only": True,
                                      "alerts": [store.get(key) for key in store.alerts]})
        if path.startswith("/alerts/"):
            key = path.removeprefix("/alerts/")
            if key in store.alerts:
                return self.respond(200, store.get(key))
        self.respond(404, {"error": "Alert or route not found"})

    def do_POST(self):
        if not self.allowed():
            return
        path = urlsplit(self.path).path.split("/")
        if len(path) != 4 or path[1] != "alerts" or path[3] not in {"review", "notes"}:
            return self.respond(404, {"error": "Review route not found"})
        if self.headers.get_content_type() != "application/json":
            return self.respond(415, {"error": "Expected application/json"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 8192:
                return self.respond(400, {"error": "Expected a JSON body of at most 8192 bytes"})
            body = json.loads(self.rfile.read(size))
            if path[2] not in self.server.store.alerts:
                raise KeyError(path[2])
            if path[3] == "notes":
                if not isinstance(body, dict) or set(body) != {"note"}:
                    raise ValueError("Expected a note.")
                return self.respond(200, self.server.store.add_note(path[2], body["note"]))
            if not isinstance(body, dict) or set(body) != {"outcome"}:
                raise ValueError("Expected exactly one outcome field")
            result = self.server.store.set_outcome(path[2], body["outcome"])
        except KeyError:
            return self.respond(404, {"error": "Alert not found"})
        except (ValueError, TimeoutError):
            return self.respond(400, {"error": "Invalid note or review outcome."})
        self.respond(200, result)


def review_server(data_dir, database, port=8765):
    store = ReviewStore(data_dir, database)
    server = HTTPServer(("127.0.0.1", port), ReviewHandler)
    server.store = store
    return server


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data/phase1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    database = Path(args.data_dir) / "review" / "reviews.sqlite3"
    with review_server(args.data_dir, database, args.port) as server:
        print(f"Synthetic review API: http://127.0.0.1:{server.server_port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
