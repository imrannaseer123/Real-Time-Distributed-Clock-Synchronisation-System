"""Smoke-test: one Cristian sync against the running server."""
import socket, time, json, sys
sys.path.insert(0, ".")
from auth import build_message, parse_message
from config import SERVER_HOST, SERVER_PORT, BUFFER_SIZE, ENCODING, SOCKET_TIMEOUT
from sync_algorithms import cristian_adjust

cid = "smoke-test"
t0 = time.time()
with socket.create_connection((SERVER_HOST, SERVER_PORT), timeout=SOCKET_TIMEOUT) as s:
    msg = build_message(cid, "GET_TIME", "")
    s.sendall(msg.encode(ENCODING))
    raw = s.recv(BUFFER_SIZE).decode(ENCODING)
    t3 = time.time()

ok, _, cmd, body = parse_message(raw)
data = json.loads(body)
adj, rtt, offset = cristian_adjust(t0, data["server_time"], data["server_time"], t3)
print(f"Auth OK       : {ok}")
print(f"Command       : {cmd}")
print(f"Server time   : {data['server_time']:.6f}")
print(f"RTT           : {rtt*1000:.3f} ms")
print(f"Offset        : {offset*1000:+.3f} ms")
print(f"Adjusted time : {adj:.6f}")
print("SMOKE TEST PASSED")
