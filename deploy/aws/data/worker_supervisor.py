"""Supervise the unchanged durable worker and publish a content-free heartbeat."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def main():
    child = subprocess.Popen([sys.executable, "/app/scripts/run_v2_worker.py"])
    stopping = [False]

    def stop(_signal, _frame):
        stopping[0] = True
        child.send_signal(signal.SIGTERM)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    target = Path("/tmp/worker-heartbeat.json")
    deadline = None
    while child.poll() is None:
        if stopping[0] and deadline is None:
            deadline = time.monotonic() + 345
        if deadline and time.monotonic() > deadline:
            child.kill()
            break
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps({"pid": child.pid, "unix": time.time()}))
        temporary.replace(target)
        time.sleep(2)
    target.unlink(missing_ok=True)
    return child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
