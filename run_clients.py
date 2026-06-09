"""
run_clients.py – Launch 5 clock-sync clients simultaneously
════════════════════════════════════════════════════════════

Spawns client-0 … client-4 as subprocesses, each in its own terminal-like
thread, so all output appears in one place with a tagged prefix.

Usage:
    python run_clients.py                  # 5 Cristian clients
    python run_clients.py --algo berkeley  # 5 Berkeley clients
    python run_clients.py --n 3            # 3 Cristian clients
"""

import argparse
import subprocess
import sys
import threading
import time


COLOURS = ["\033[93m", "\033[92m", "\033[96m", "\033[95m", "\033[91m"]
RESET   = "\033[0m"


def stream_output(proc: subprocess.Popen, prefix: str, colour: str):
    """Forward a subprocess's stdout line-by-line with a coloured prefix."""
    for line in proc.stdout:
        print(f"{colour}{prefix}{RESET} {line}", end="", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Launch multiple clock-sync clients")
    parser.add_argument("--n",    type=int, default=5,         help="Number of clients (default 5)")
    parser.add_argument("--algo", default="cristian",          help="Algorithm: cristian|berkeley")
    args = parser.parse_args()

    procs   = []
    readers = []

    print(f"\n🕐  Launching {args.n} clients using [{args.algo.upper()}] algorithm…\n")
    time.sleep(0.5)

    for i in range(args.n):
        cid  = f"client-{i}"
        port = 9100 + i
        cmd  = [
            sys.executable, "client.py",
            "--id",   cid,
            "--port", str(port),
            "--algo", args.algo,
        ]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        procs.append(proc)

        colour = COLOURS[i % len(COLOURS)]
        t = threading.Thread(
            target=stream_output,
            args=(proc, f"[{cid}]", colour),
            daemon=True,
        )
        t.start()
        readers.append(t)
        time.sleep(0.2)  # stagger slightly so ports don't collide

    print(f"✅  All {args.n} clients launched. Press Ctrl+C to stop.\n")

    try:
        # Wait until all children exit (they run forever until killed)
        for proc in procs:
            proc.wait()
    except KeyboardInterrupt:
        print("\n⚠️  Stopping all clients…")
        for proc in procs:
            proc.terminate()
        for proc in procs:
            proc.wait()
        print("✅  All clients stopped.")


if __name__ == "__main__":
    main()
