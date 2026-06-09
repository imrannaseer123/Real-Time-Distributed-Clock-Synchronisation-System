"""
config.py - Central configuration for the Distributed Clock Synchronization System
"""

# ─── Server / Network ───────────────────────────────────────────────────────
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 9000          # Primary time-server port
DASHBOARD_PORT = 5050       # Flask dashboard port

# Client port range (each client binds its own port for Berkeley callbacks)
CLIENT_BASE_PORT = 9100     # client-0 → 9100, client-1 → 9101, …

# ─── Sync Settings ──────────────────────────────────────────────────────────
SYNC_INTERVAL_SECONDS = 5   # How often clients re-sync
MAX_DRIFT_SECONDS = 2.0     # Max random drift injected per cycle (±)
HISTORY_MAX_POINTS = 50     # Chart data-points retained per client

# ─── Algorithm ──────────────────────────────────────────────────────────────
# "cristian" or "berkeley"
DEFAULT_ALGORITHM = "cristian"

# Berkeley coordinator port (server acts as coordinator)
BERKELEY_PORT = 9001

# ─── Authentication ──────────────────────────────────────────────────────────
# Simple shared-secret token; clients must send this in every request.
AUTH_TOKEN = "CLOCK_SYNC_SECRET_2024"

# ─── Logging ─────────────────────────────────────────────────────────────────
LOG_FILE = "logs/sync_log.csv"
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(message)s"

# ─── Socket Settings ─────────────────────────────────────────────────────────
SOCKET_TIMEOUT = 5          # seconds
BUFFER_SIZE = 4096
ENCODING = "utf-8"
