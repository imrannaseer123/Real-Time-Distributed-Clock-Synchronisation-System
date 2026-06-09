# Real-Time Distributed Clock Synchronisation System

A Python implementation of Cristian's Algorithm and the Berkeley Algorithm for
distributed clock synchronisation, complete with a real-time web dashboard.

---

## Quick Start (4 terminals)

```
Terminal 1 – Time Server
  python server.py

Terminal 2 – 5 Cristian clients (auto-launched)
  python run_clients.py

Terminal 3 – Dashboard (optional)
  python dashboard/app.py

Browser
  http://127.0.0.1:5050
```

---

## Running individual clients

```bash
# Cristian's Algorithm (default)
python client.py --id client-0
python client.py --id client-1
python client.py --id client-2

# Berkeley Algorithm
python client.py --id client-0 --algo berkeley
python client.py --id client-1 --algo berkeley
```

---

## Switching algorithms

**Cristian** (default, per-client pull):
```bash
python run_clients.py --algo cristian
```

**Berkeley** (coordinator-pushed):
```bash
python run_clients.py --algo berkeley
```

---

## File Structure

```
distributed-clock-sync/
├── config.py           # Central configuration (ports, tokens, intervals)
├── auth.py             # HMAC-SHA256 authentication
├── sync_algorithms.py  # Cristian + Berkeley pure logic
├── server.py           # Time server (Cristian + Berkeley coordinator + Dashboard API)
├── client.py           # Client node with drift simulation
├── run_clients.py      # Multi-client launcher
├── requirements.txt    # pip deps (only flask)
├── logs/
│   └── sync_log.csv    # Sync event log (auto-created)
└── dashboard/
    ├── app.py              # Flask web server
    ├── templates/index.html
    └── static/
        ├── style.css
        └── dashboard.js
```

---

## Algorithm Details

### Cristian's Algorithm
1. Client records `t0 = time.time()` then sends `GET_TIME` to server.
2. Server replies with its timestamp `T_server`.
3. Client records `t3 = time.time()` on receipt.
4. `RTT = t3 − t0`
5. `Adjusted Time = T_server + RTT / 2`
6. `Offset = Adjusted Time − t3` → applied to local drift.

### Berkeley Algorithm
1. Server coordinator sends `GET_CLIENT_TIME` to all registered clients.
2. Each client replies with its drifted time.
3. Coordinator computes average (discarding outliers > 2σ).
4. Sends `APPLY_OFFSET` to each client with their individual delta.

---

## Security

Every wire message is structured as:
```
AUTH:<client_id>:<unix_timestamp>:<HMAC-SHA256>\n
<COMMAND>\n
<JSON body>
```
- HMAC-SHA256 signed with `AUTH_TOKEN` from `config.py`.
- Timestamps expire after 30 s (replay attack prevention).
- Server rejects any message with an invalid signature.

---

## Configuration (`config.py`)

| Key | Default | Description |
|-----|---------|-------------|
| `SERVER_HOST` | `127.0.0.1` | Bind address |
| `SERVER_PORT` | `9000` | Cristian server port |
| `BERKELEY_PORT` | `9001` | Berkeley coordinator port |
| `DASHBOARD_PORT` | `5050` | Web dashboard |
| `SYNC_INTERVAL_SECONDS` | `5` | How often clients sync |
| `MAX_DRIFT_SECONDS` | `2.0` | Initial max random drift |
| `AUTH_TOKEN` | `CLOCK_SYNC_SECRET_2024` | Shared secret |

---

## Logs

Synchronisation events are written to `logs/sync_log.csv`:

```
timestamp, event, client_id, algorithm, rtt_ms, offset_ms, server_time, client_time
```
