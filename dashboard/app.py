"""
dashboard/app.py – Flask web dashboard for the clock-sync system
════════════════════════════════════════════════════════════════

Serves a real-time HTML page that:
  • Polls the server's JSON API (SERVER_PORT + 2) every 2 seconds.
  • Reads the CSV log for chart history.
  • Exposes /api/state and /api/history as REST endpoints the page
    fetches with XHR/fetch.

Usage:
    python dashboard/app.py
"""

import csv
import json
import os
import socket
import sys
import time
from pathlib import Path

# Allow importing from parent directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, jsonify, render_template, send_from_directory

from config import (
    BUFFER_SIZE, DASHBOARD_PORT, ENCODING, LOG_FILE,
    SERVER_HOST, SERVER_PORT, SOCKET_TIMEOUT,
)

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["JSON_SORT_KEYS"] = False


# ─── Helpers ──────────────────────────────────────────────────────────────────

def fetch_server_state() -> dict:
    """Pull live state from the server's Dashboard API socket."""
    try:
        with socket.create_connection(
            (SERVER_HOST, SERVER_PORT + 2), timeout=SOCKET_TIMEOUT
        ) as s:
            s.sendall(b"GET_STATE")
            chunks = []
            while True:
                chunk = s.recv(BUFFER_SIZE)
                if not chunk:
                    break
                chunks.append(chunk)
            raw = b"".join(chunks).decode(ENCODING)
            return json.loads(raw)
    except Exception as exc:
        return {"error": str(exc), "server_time": time.time(), "clients": {}}


def read_csv_history(max_rows: int = 200) -> list:
    """Read recent rows from the CSV log file."""
    rows = []
    log_path = Path(__file__).parent.parent / LOG_FILE
    if not log_path.exists():
        return rows
    try:
        with open(log_path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
        return rows[-max_rows:]
    except Exception:
        return rows


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/state")
def api_state():
    """Live JSON state from the server."""
    return jsonify(fetch_server_state())


@app.route("/api/history")
def api_history():
    """CSV history as JSON for the charts."""
    return jsonify(read_csv_history())


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\n🌐  Dashboard running at  http://{SERVER_HOST}:{DASHBOARD_PORT}")
    print(f"    Polling server state from {SERVER_HOST}:{SERVER_PORT + 2}\n")
    app.run(host=SERVER_HOST, port=DASHBOARD_PORT, debug=False)
