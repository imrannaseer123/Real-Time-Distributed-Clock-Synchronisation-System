"""
sync_algorithms.py
──────────────────
Pure-logic implementations of two classic clock-synchronisation algorithms.

  • Cristian's Algorithm  – client/server model, single RTT adjustment.
  • Berkeley Algorithm    – coordinator gathers all clocks, sends offsets.

No socket code lives here; these functions accept / return plain numbers so
they can be unit-tested in isolation.
"""

import statistics
from typing import Dict, List, Tuple


# ═══════════════════════════════════════════════════════════════════════════════
# Cristian's Algorithm
# ═══════════════════════════════════════════════════════════════════════════════

def cristian_adjust(
    t0: float,          # client local time  when request  was sent
    t1: float,          # server local time  when it received the request (unused here –
                        #  we only need the server's *reply* time, T_server)
    t_server: float,    # server local time  embedded in its reply
    t3: float,          # client local time  when reply arrived
) -> Tuple[float, float, float]:
    """
    Compute the adjusted client time using Cristian's algorithm.

    T_corrected = T_server + RTT / 2

    Returns
    -------
    (adjusted_time, rtt, offset)
        adjusted_time  – the best estimate of "true" current time
        rtt            – measured round-trip time in seconds
        offset         – how much the client clock was off
    """
    rtt = t3 - t0                           # full round-trip time
    adjusted_time = t_server + rtt / 2      # best estimate of current server time
    offset = adjusted_time - t3             # how far the local clock is wrong
    return adjusted_time, rtt, offset


# ═══════════════════════════════════════════════════════════════════════════════
# Berkeley Algorithm
# ═══════════════════════════════════════════════════════════════════════════════

def berkeley_compute_offsets(
    coordinator_time: float,
    client_times: Dict[str, float],
    fault_tolerance_sigma: float = 2.0,
) -> Tuple[float, Dict[str, float]]:
    """
    Berkeley Algorithm – coordinator side.

    Steps
    -----
    1. Gather each client's reported time.
    2. Compute the mean of all times (coordinator + clients).
    3. Optionally discard outliers beyond *fault_tolerance_sigma* std-deviations.
    4. Return the average and per-node offset adjustments.

    Parameters
    ----------
    coordinator_time     : coordinator's own current time
    client_times         : {client_id: reported_time}
    fault_tolerance_sigma: outliers further than this many σ are discarded

    Returns
    -------
    (average_time, offsets)
        average_time – the target consensus time
        offsets      – {node_id: delta}  positive ⟹ node must move clock forward
    """
    all_times: Dict[str, float] = {"coordinator": coordinator_time}
    all_times.update(client_times)

    times_list = list(all_times.values())

    # Remove outliers if we have enough samples
    if len(times_list) >= 3:
        mean = statistics.mean(times_list)
        stdev = statistics.stdev(times_list) or 1e-9
        filtered = {
            nid: t
            for nid, t in all_times.items()
            if abs(t - mean) <= fault_tolerance_sigma * stdev
        }
    else:
        filtered = all_times

    average_time = statistics.mean(filtered.values())

    # Compute individual offsets
    offsets = {nid: average_time - t for nid, t in all_times.items()}
    return average_time, offsets


def berkeley_apply_offset(local_time: float, offset: float) -> float:
    """
    Client side: apply the coordinator-supplied offset.

    Returns the corrected local time.
    """
    return local_time + offset


# ═══════════════════════════════════════════════════════════════════════════════
# Drift simulation helper
# ═══════════════════════════════════════════════════════════════════════════════

import random


def simulate_drift(current_offset: float, max_new_drift: float = 0.5) -> float:
    """
    Add a small random walk component to the existing offset.

    This mimics real hardware clock drift which accumulates over time.
    """
    delta = random.uniform(-max_new_drift, max_new_drift)
    # Clamp total drift to ±5 s so the simulation remains readable
    return max(-5.0, min(5.0, current_offset + delta))
