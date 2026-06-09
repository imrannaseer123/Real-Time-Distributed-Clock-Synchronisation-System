"""
client.py – Clock-Sync Client Node
═══════════════════════════════════

Each client:
  • Starts with a random clock drift (offset from true time).
  • Periodically syncs using Cristian's Algorithm or Berkeley Algorithm.
  • Reports sync results back to the server for logging.
  • Exposes a tiny callback socket so the Berkeley coordinator can reach it.
  • Prints a coloured before/after table to the terminal.

Usage (Cristian, auto-select port):
    python client.py --id client-0

Usage (Berkeley):
    python client.py --id client-0 --algo berkeley

Usage (explicit callback port):
    python client.py --id client-2 --port 9102 --algo cristian
"""

import argparse
import json
import logging
import random
import socket
import threading
import time
from datetime import datetime

from auth import build_message, parse_message
from config import (
    BERKELEY_PORT, BUFFER_SIZE, CLIENT_BASE_PORT, ENCODING,
    LOG_FORMAT, MAX_DRIFT_SECONDS, SERVER_HOST, SERVER_PORT,
    SOCKET_TIMEOUT, SYNC_INTERVAL_SECONDS,
)
from sync_algorithms import cristian_adjust, berkeley_apply_offset, simulate_drift

# ─── Colour helpers (ANSI – work on Linux/macOS; Windows needs VT mode) ───────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


def coloured(text: str, colour: str) -> str:
    return f"{colour}{text}{RESET}"


# ─── Logger ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)


class ClockClient:
    """
    A simulated distributed-system node with an intentionally drifting clock.

    Attributes
    ----------
    client_id   : unique name, e.g. "client-0"
    drift       : accumulated offset (seconds) added to time.time() reads
    callback_port: TCP port this node listens on for Berkeley callbacks
    algorithm   : "cristian" or "berkeley"
    """

    def __init__(self, client_id: str, callback_port: int, algorithm: str = "cristian"):
        self.client_id     = client_id
        self.algorithm     = algorithm
        self.callback_port = callback_port
        self.logger        = logging.getLogger(client_id)

        # Simulate initial clock drift  ±MAX_DRIFT_SECONDS
        self.drift: float = random.uniform(-MAX_DRIFT_SECONDS, MAX_DRIFT_SECONDS)
        self.logger.info(
            "Initial drift: %+.3f s (local clock is %s)",
            self.drift,
            "fast" if self.drift > 0 else "slow",
        )

        # Sync history for the dashboard  [{timestamp, before, after, offset, rtt}]
        self._history: list = []
        self._history_lock = threading.Lock()

        # Berkeley: flag to signal coordinator is pushing an offset
        self._berkeley_offset_event = threading.Event()
        self._pending_offset: float = 0.0

    # ─── "Local" clock ───────────────────────────────────────────────────────

    def local_time(self) -> float:
        """Return simulated drifted clock time."""
        return time.time() + self.drift

    def adjust_clock(self, delta: float):
        """Apply a delta correction to our drifted local clock."""
        self.drift += delta

    # ─── Cristian sync ───────────────────────────────────────────────────────

    def sync_cristian(self):
        """Perform one Cristian Algorithm sync round."""
        before = self.local_time()

        try:
            with socket.create_connection(
                (SERVER_HOST, SERVER_PORT), timeout=SOCKET_TIMEOUT
            ) as s:
                # ── 1. Send GET_TIME ──────────────────────────────────────
                t0 = time.time()
                msg = build_message(self.client_id, "GET_TIME", "")
                s.sendall(msg.encode(ENCODING))

                # ── 2. Receive server time ────────────────────────────────
                raw = s.recv(BUFFER_SIZE).decode(ENCODING)
                t3 = time.time()

            auth_ok, _, command, body = parse_message(raw)
            if not auth_ok or command != "TIME_RESPONSE":
                self.logger.error("Unexpected response: %s", raw[:80])
                return

            data = json.loads(body)
            t_server = data["server_time"]

            # ── 3. Cristian adjustment ────────────────────────────────────
            adjusted_time, rtt, offset = cristian_adjust(
                t0=t0, t1=t_server, t_server=t_server, t3=t3
            )

            # Apply correction to our drifted clock
            self.adjust_clock(offset)
            after = self.local_time()

            self._print_sync_table("Cristian", before, after, rtt, offset)
            self._record_history(before, after, rtt, offset)

            # ── 4. Report back to server ──────────────────────────────────
            self._send_sync_report(rtt, offset, t_server)

        except Exception as exc:
            self.logger.error("Cristian sync failed: %s", exc)

    def _send_sync_report(self, rtt: float, offset: float, server_time: float):
        """Send RTT/offset data back to server for central logging."""
        try:
            with socket.create_connection(
                (SERVER_HOST, SERVER_PORT), timeout=SOCKET_TIMEOUT
            ) as s:
                body = json.dumps({
                    "rtt":         rtt,
                    "offset":      offset,
                    "drift":       self.drift,
                    "client_time": self.local_time(),
                    "server_time": server_time,
                })
                msg = build_message(self.client_id, "SYNC_REPORT", body)
                s.sendall(msg.encode(ENCODING))
                s.recv(BUFFER_SIZE)  # wait for OK
        except Exception:
            pass  # Best-effort; don't abort on logging failure

    # ─── Berkeley sync ────────────────────────────────────────────────────────

    def register_with_berkeley(self):
        """Tell the coordinator that we exist and our callback port."""
        try:
            with socket.create_connection(
                (SERVER_HOST, BERKELEY_PORT), timeout=SOCKET_TIMEOUT
            ) as s:
                body = json.dumps({"callback_port": self.callback_port})
                msg = build_message(self.client_id, "REGISTER", body)
                s.sendall(msg.encode(ENCODING))
                resp = s.recv(BUFFER_SIZE)
                if resp == b"OK":
                    self.logger.info("Registered with Berkeley coordinator")
                else:
                    self.logger.warning("Berkeley registration failed: %s", resp)
        except Exception as exc:
            self.logger.error("Berkeley registration error: %s", exc)

    def run_berkeley_callback_server(self):
        """
        Listen for two types of messages from the coordinator:
          • GET_CLIENT_TIME → reply with our current drifted time.
          • APPLY_OFFSET    → adjust our clock.
        """
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((SERVER_HOST, self.callback_port))
        srv.listen(5)
        self.logger.info("Berkeley callback listening on port %d", self.callback_port)

        while True:
            try:
                conn, _ = srv.accept()
                threading.Thread(
                    target=self._handle_berkeley_message,
                    args=(conn,), daemon=True,
                ).start()
            except Exception as exc:
                self.logger.error("Callback server error: %s", exc)

    def _handle_berkeley_message(self, conn: socket.socket):
        try:
            raw = conn.recv(BUFFER_SIZE).decode(ENCODING)
            auth_ok, sender, command, body = parse_message(raw)

            if not auth_ok:
                conn.sendall(b"ERROR:AUTH")
                return

            if command == "GET_CLIENT_TIME":
                # Phase 1: report our current clock
                payload = json.dumps({"time": self.local_time()})
                reply = build_message(self.client_id, "CLIENT_TIME", payload)
                conn.sendall(reply.encode(ENCODING))

            elif command == "APPLY_OFFSET":
                # Phase 3: apply the coordinator's correction
                data = json.loads(body)
                offset = data["offset"]
                avg_time = data["average_time"]

                before = self.local_time()
                self.adjust_clock(offset)
                after = self.local_time()

                self.logger.info(
                    "[Berkeley] Offset %+.3fs applied | before=%.3f after=%.3f",
                    offset, before, after,
                )
                self._print_sync_table("Berkeley", before, after, 0, offset)
                self._record_history(before, after, 0, offset)
                conn.sendall(b"OK")

        except Exception as exc:
            self.logger.error("Berkeley message handler error: %s", exc)
        finally:
            conn.close()

    # ─── Drift injection loop ────────────────────────────────────────────────

    def drift_loop(self):
        """Continuously add random drift to simulate hardware clock wandering."""
        while True:
            time.sleep(SYNC_INTERVAL_SECONDS)
            self.drift = simulate_drift(self.drift, max_new_drift=0.3)
            self.logger.debug("Clock drift now: %+.3fs", self.drift)

    # ─── Main sync loop ──────────────────────────────────────────────────────

    def run_sync_loop(self):
        """Periodic synchronisation – runs forever."""
        while True:
            if self.algorithm == "cristian":
                self.sync_cristian()
            elif self.algorithm == "berkeley":
                # Berkeley is coordinator-pushed; just keep running drift
                pass
            time.sleep(SYNC_INTERVAL_SECONDS)

    # ─── History helpers ─────────────────────────────────────────────────────

    def _record_history(self, before: float, after: float, rtt: float, offset: float):
        entry = {
            "ts":       datetime.utcnow().isoformat(),
            "before":   round(before, 6),
            "after":    round(after, 6),
            "rtt_ms":   round(rtt * 1000, 3),
            "offset_ms": round(offset * 1000, 3),
            "drift":    round(self.drift, 6),
        }
        with self._history_lock:
            self._history.append(entry)
            if len(self._history) > 50:
                self._history = self._history[-50:]

    def get_history(self) -> list:
        with self._history_lock:
            return list(self._history)

    # ─── Pretty print ────────────────────────────────────────────────────────

    def _print_sync_table(
        self, algo: str, before: float, after: float, rtt: float, offset: float
    ):
        fmt = datetime.utcfromtimestamp
        sep = "─" * 52
        drift_sign = "▲" if self.drift > 0 else "▼"
        print(
            f"\n{BOLD}{CYAN}{sep}{RESET}\n"
            f"  {BOLD}[{self.client_id}]{RESET}  algorithm={CYAN}{algo}{RESET}\n"
            f"  Before : {YELLOW}{fmt(before)}{RESET}\n"
            f"  After  : {GREEN}{fmt(after)}{RESET}\n"
            f"  RTT    : {rtt*1000:.2f} ms\n"
            f"  Offset : {coloured(f'{offset*1000:+.3f} ms', GREEN if abs(offset)<0.01 else YELLOW)}\n"
            f"  Drift  : {drift_sign} {abs(self.drift):.3f} s\n"
            f"{BOLD}{CYAN}{sep}{RESET}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Entry-point
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Distributed Clock Sync – Client")
    parser.add_argument("--id",   default="client-0", help="Unique client identifier")
    parser.add_argument("--port", type=int, default=None,
                        help="Callback port (auto-assigned from CLIENT_BASE_PORT if omitted)")
    parser.add_argument(
        "--algo", choices=["cristian", "berkeley"], default="cristian",
        help="Sync algorithm to use",
    )
    args = parser.parse_args()

    # Auto-assign port from client index if not specified
    if args.port is None:
        try:
            idx = int(args.id.split("-")[-1])
        except ValueError:
            idx = random.randint(0, 99)
        args.port = CLIENT_BASE_PORT + idx

    client = ClockClient(
        client_id=args.id,
        callback_port=args.port,
        algorithm=args.algo,
    )

    threads = []

    # Always run a drift loop
    threads.append(threading.Thread(target=client.drift_loop, daemon=True, name="Drift"))

    if args.algo == "cristian":
        threads.append(threading.Thread(target=client.run_sync_loop, daemon=True, name="SyncLoop"))
    else:
        # Berkeley: spin up callback server and register
        threads.append(
            threading.Thread(target=client.run_berkeley_callback_server, daemon=True, name="BerkeleyCallback")
        )
        # Give the callback server a moment to bind before registering
        def _register_later():
            time.sleep(1)
            client.register_with_berkeley()
        threads.append(threading.Thread(target=_register_later, daemon=True, name="BerkeleyReg"))

    for t in threads:
        t.start()

    print(
        f"\n{BOLD}[{args.id}]{RESET} started | algorithm={CYAN}{args.algo}{RESET} "
        f"| callback port={args.port}\n"
        f"Syncing every {SYNC_INTERVAL_SECONDS}s. Press Ctrl+C to stop.\n"
    )

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\n[{args.id}] Shutting down.")


if __name__ == "__main__":
    main()
