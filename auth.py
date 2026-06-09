"""
auth.py - Simple shared-secret authentication for the clock-sync system.

Every message that travels between nodes must start with the AUTH_TOKEN.
The helper functions here encode / validate tokens so the rest of the
codebase never has to touch raw tokens directly.
"""

import hashlib
import hmac
import time

from config import AUTH_TOKEN, ENCODING


# ─── Token helpers ───────────────────────────────────────────────────────────

def _sign(payload: str) -> str:
    """Return HMAC-SHA256 hex digest of *payload* using the shared secret."""
    return hmac.new(
        AUTH_TOKEN.encode(ENCODING),
        payload.encode(ENCODING),
        hashlib.sha256,
    ).hexdigest()


def create_auth_header(client_id: str) -> str:
    """
    Build an auth header string:
        AUTH:<client_id>:<unix_timestamp>:<hmac>
    The timestamp is included so replayed packets expire quickly.
    """
    ts = str(int(time.time()))
    payload = f"{client_id}:{ts}"
    signature = _sign(payload)
    return f"AUTH:{client_id}:{ts}:{signature}"


def validate_auth_header(header: str, max_age_seconds: int = 30) -> tuple[bool, str]:
    """
    Validate an auth header returned by *create_auth_header*.

    Returns (True, client_id) on success, (False, reason) on failure.
    """
    try:
        parts = header.split(":")
        if len(parts) != 4 or parts[0] != "AUTH":
            return False, "Malformed header"

        _, client_id, ts_str, received_sig = parts
        ts = int(ts_str)

        # Reject stale tokens
        age = int(time.time()) - ts
        if age > max_age_seconds or age < -5:          # small skew allowed
            return False, f"Token expired (age={age}s)"

        # Verify HMAC
        expected_sig = _sign(f"{client_id}:{ts_str}")
        if not hmac.compare_digest(expected_sig, received_sig):
            return False, "Invalid signature"

        return True, client_id

    except Exception as exc:
        return False, f"Auth error: {exc}"


def build_message(client_id: str, command: str, body: str = "") -> str:
    """
    Assemble a complete wire message:
        <auth_header>\n<command>\n<body>
    """
    header = create_auth_header(client_id)
    return f"{header}\n{command}\n{body}"


def parse_message(raw: str) -> tuple[bool, str, str, str]:
    """
    Decompose a wire message from *build_message*.

    Returns (auth_ok, client_id_or_reason, command, body).
    """
    lines = raw.strip().split("\n", 2)
    if len(lines) < 2:
        return False, "Truncated message", "", ""

    auth_header = lines[0]
    command = lines[1] if len(lines) > 1 else ""
    body = lines[2] if len(lines) > 2 else ""

    auth_ok, result = validate_auth_header(auth_header)
    return auth_ok, result, command, body
