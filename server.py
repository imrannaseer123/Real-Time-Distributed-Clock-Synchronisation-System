"""
server.py – Time Server for the Distributed Clock Synchronisation System
═════════════════════════════════════════════════════════════════════════

Responsibilities
────────────────
• Listens on SERVER_PORT for Cristian-style GET_TIME requests.
• Listens on BERKELEY_PORT for Berkeley-style COLLECT_TIME / SEND_OFFSETS.
• Maintains an in-memory registry of connected clients (id, last sync time,
  drift, RTT, algorithm) that the dashboard can query via a third socket
  (SERVER_PORT + 2, JSON API).
• Logs every synchronisation event to logs/sync_log.csv.
• Authenticates every incoming message with the shared HMAC token.

Usage
─────
    python server.py [--algo cristian|berkeley]
"""

import argparse
import csv
import json
import logging
import os
import socket
import threading
import time
from datetime import datetime
from typing import Dict

from auth import parse_message, build_message
from config import (
    AUTH_TOKEN, BERKELEY_PORT, BUFFER_SIZE, ENCODING,
    LOG_FILE, LOG_FORMAT, SERVER_HOST, SERVER_PORT, SOCKET_TIMEOUT,
)
from sync_algorithms import berkeley_compute_offsets

# ─── Logging setup ────────────────────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger("Server")

# ─── CSV log ──────────────────────────────────────────────────────────────────
csv_lock = threading.Lock()
_csv_header_written = os.path.exists(LOG_FILE)

def log_csv(event: str, client_id: str, algorithm: str,
            rtt: float, offset: float, server_time: float, client_time: float):
    """Append one row to the CSV sync log."""
    global _csv_header_written
    with csv_lock:
        with open(LOG_FILE, "a", newline="") as f:
            writer = csv.writer(f)
            if not _csv_header_written:
                writer.writerow([
                    "timestamp", "event", "client_id", "algorithm",
                    "rtt_ms", "offset_ms", "server_time", "client_time",
                ])
                _csv_header_written = True
            writer.writerow([
                datetime.utcnow().isoformat(), event, client_id, algorithm,
                round(rtt * 1000, 3), round(offset * 1000, 3),
                round(server_time, 6), round(client_time, 6),
            ])


# ─── Shared state (thread-safe via lock) ─────────────────────────────────────
state_lock = threading.Lock()
# client_registry: { client_id: { last_sync, rtt_ms, offset_ms, algorithm,
#                                  client_time, server_time, drift } }
client_registry: Dict[str, dict] = {}


def update_registry(client_id: str, **kwargs):
    with state_lock:
        if client_id not in client_registry:
            client_registry[client_id] = {}
        client_registry[client_id].update(kwargs)
        client_registry[client_id]["last_sync"] = datetime.utcnow().isoformat()


# ═══════════════════════════════════════════════════════════════════════════════
# Cristian's time-server thread
# ═══════════════════════════════════════════════════════════════════════════════

def handle_cristian_client(conn: socket.socket, addr):
    """Handle a single Cristian GET_TIME request from one client."""
    try:
        raw = conn.recv(BUFFER_SIZE).decode(ENCODING)
        auth_ok, client_id_or_reason, command, body = parse_message(raw)

        if not auth_ok:
            logger.warning("Auth FAILED from %s: %s", addr, client_id_or_reason)
            conn.sendall(b"ERROR:AUTH_FAILED")
            return

        client_id = client_id_or_reason

        if command == "GET_TIME":
            server_time = time.time()                       # capture server time
            response_body = json.dumps({
                "server_time": server_time,
                "algorithm": "cristian",
            })
            msg = build_message("server", "TIME_RESPONSE", response_body)
            conn.sendall(msg.encode(ENCODING))

            # Log (RTT/offset calculated on client; we just log what we know)
            logger.info("[Cristian] Served time %.6f to %s", server_time, client_id)
            log_csv("TIME_SERVED", client_id, "cristian", 0, 0, server_time, 0)
            update_registry(client_id, algorithm="cristian",
                            server_time=server_time, rtt_ms=0, offset_ms=0)

        elif command == "SYNC_REPORT":
            # Clients send back their RTT / offset for logging
            data = json.loads(body) if body else {}
            rtt   = data.get("rtt", 0)
            offset = data.get("offset", 0)
            drift  = data.get("drift", 0)
            ct     = data.get("client_time", 0)
            st     = data.get("server_time", 0)

            logger.info(
                "[Cristian] %s | RTT=%.1fms | offset=%.1fms | drift=%.3fs",
                client_id, rtt * 1000, offset * 1000, drift,
            )
            log_csv("SYNC_REPORT", client_id, "cristian", rtt, offset, st, ct)
            update_registry(client_id, algorithm="cristian", rtt_ms=rtt * 1000,
                            offset_ms=offset * 1000, drift=drift,
                            server_time=st, client_time=ct)
            conn.sendall(b"OK")

        else:
            conn.sendall(b"ERROR:UNKNOWN_COMMAND")

    except Exception as exc:
        logger.error("Cristian handler error: %s", exc)
    finally:
        conn.close()


def run_cristian_server():
    """Blocking listener for Cristian-style requests."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((SERVER_HOST, SERVER_PORT))
    srv.listen(20)
    logger.info("Cristian Time-Server listening on %s:%d", SERVER_HOST, SERVER_PORT)

    while True:
        conn, addr = srv.accept()
        conn.settimeout(SOCKET_TIMEOUT)
        t = threading.Thread(
            target=handle_cristian_client, args=(conn, addr), daemon=True
        )
        t.start()


# ═══════════════════════════════════════════════════════════════════════════════
# Berkeley Algorithm coordinator thread
# ═══════════════════════════════════════════════════════════════════════════════

def run_berkeley_coordinator():
    """
    Berkeley coordinator loop.

    Every SYNC_INTERVAL seconds the coordinator:
      1. Sends TIME_REQUEST to every known client.
      2. Collects their clock readings.
      3. Computes average + offsets.
      4. Pushes offset adjustments back to each client.
    """
    import time as _time
    from config import SYNC_INTERVAL_SECONDS, CLIENT_BASE_PORT

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((SERVER_HOST, BERKELEY_PORT))
    srv.listen(20)
    logger.info("Berkeley Coordinator listening on %s:%d", SERVER_HOST, BERKELEY_PORT)

    # Map of client_id → their listening port for callback
    client_ports: Dict[str, int] = {}

    def handle_registration(conn, addr):
        """Clients first register their callback port."""
        try:
            raw = conn.recv(BUFFER_SIZE).decode(ENCODING)
            auth_ok, client_id, command, body = parse_message(raw)
            if not auth_ok:
                conn.sendall(b"ERROR:AUTH_FAILED")
                return
            if command == "REGISTER":
                data = json.loads(body)
                port = data["callback_port"]
                with state_lock:
                    client_ports[client_id] = port
                logger.info("[Berkeley] Registered %s on callback port %d", client_id, port)
                conn.sendall(b"OK")
        except Exception as exc:
            logger.error("Berkeley registration error: %s", exc)
        finally:
            conn.close()

    def berkeley_round():
        """Perform one full Berkeley synchronisation round."""
        with state_lock:
            snapshot = dict(client_ports)

        if not snapshot:
            return

        coordinator_time = _time.time()
        client_times: Dict[str, float] = {}

        # ── Phase 1: collect client times ────────────────────────────────────
        for cid, port in snapshot.items():
            try:
                with socket.create_connection((SERVER_HOST, port), timeout=SOCKET_TIMEOUT) as s:
                    msg = build_message("coordinator", "GET_CLIENT_TIME", "")
                    s.sendall(msg.encode(ENCODING))
                    raw = s.recv(BUFFER_SIZE).decode(ENCODING)
                    _, _, cmd, body = parse_message(raw)
                    if cmd == "CLIENT_TIME":
                        data = json.loads(body)
                        client_times[cid] = data["time"]
            except Exception as exc:
                logger.warning("[Berkeley] Could not reach %s: %s", cid, exc)

        if not client_times:
            return

        # ── Phase 2: compute average ─────────────────────────────────────────
        average_time, offsets = berkeley_compute_offsets(coordinator_time, client_times)
        logger.info(
            "[Berkeley] average=%.3f | clients=%s",
            average_time, list(client_times.keys()),
        )

        # ── Phase 3: push offsets ────────────────────────────────────────────
        for cid, port in snapshot.items():
            offset = offsets.get(cid, 0.0)
            try:
                with socket.create_connection((SERVER_HOST, port), timeout=SOCKET_TIMEOUT) as s:
                    body = json.dumps({"offset": offset, "average_time": average_time})
                    msg = build_message("coordinator", "APPLY_OFFSET", body)
                    s.sendall(msg.encode(ENCODING))
                    s.recv(BUFFER_SIZE)  # ACK

                log_csv("BERKELEY_OFFSET", cid, "berkeley", 0, offset, average_time, client_times.get(cid, 0))
                update_registry(cid, algorithm="berkeley", offset_ms=offset * 1000,
                                server_time=average_time, client_time=client_times.get(cid, 0))
            except Exception as exc:
                logger.warning("[Berkeley] Could not push offset to %s: %s", cid, exc)

    # Accept registration connections while also running rounds
    srv.settimeout(1.0)
    last_round = 0.0
    from config import SYNC_INTERVAL_SECONDS as SIV

    while True:
        # Accept incoming registrations non-blockingly
        try:
            conn, addr = srv.accept()
            conn.settimeout(SOCKET_TIMEOUT)
            threading.Thread(target=handle_registration, args=(conn, addr), daemon=True).start()
        except socket.timeout:
            pass

        now = _time.time()
        if now - last_round >= SIV:
            threading.Thread(target=berkeley_round, daemon=True).start()
            last_round = now


# ═══════════════════════════════════════════════════════════════════════════════
# Dashboard JSON API  (SERVER_PORT + 2)
# ═══════════════════════════════════════════════════════════════════════════════

def run_dashboard_api():
    """
    Tiny JSON-over-TCP endpoint so the dashboard can poll live state without
    pulling in a full HTTP library on the server side.
    """
    api_port = SERVER_PORT + 2
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((SERVER_HOST, api_port))
    srv.listen(20)
    logger.info("Dashboard API listening on %s:%d", SERVER_HOST, api_port)

    def handle(conn, _addr):
        try:
            raw = conn.recv(BUFFER_SIZE).decode(ENCODING)
            if "GET_STATE" in raw:
                with state_lock:
                    snapshot = dict(client_registry)
                payload = json.dumps({
                    "server_time": time.time(),
                    "clients": snapshot,
                })
                conn.sendall(payload.encode(ENCODING))
        except Exception:
            pass
        finally:
            conn.close()

    while True:
        conn, addr = srv.accept()
        threading.Thread(target=handle, args=(conn, addr), daemon=True).start()


# ═══════════════════════════════════════════════════════════════════════════════
# Entry-point
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Distributed Clock Sync – Time Server")
    parser.add_argument(
        "--algo", choices=["cristian", "berkeley"], default="cristian",
        help="Which algorithm to advertise (default: cristian)",
    )
    args = parser.parse_args()

    logger.info("=== Time Server starting (algorithm: %s) ===", args.algo)

    threads = [
        threading.Thread(target=run_cristian_server,     daemon=True, name="CristianSrv"),
        threading.Thread(target=run_berkeley_coordinator, daemon=True, name="BerkeleySrv"),
        threading.Thread(target=run_dashboard_api,        daemon=True, name="DashboardAPI"),
    ]
    for t in threads:
        t.start()

    logger.info("All server threads running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Server shutting down.")


if __name__ == "__main__":
    main()
