"""Content-free host/container disk and memory monitoring; no provider requests."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=Path("/srv/rag/state"))
    parser.add_argument("--project", default="rag-demo")
    args = parser.parse_args()
    disk = shutil.disk_usage(args.state)
    ids = subprocess.check_output(["docker", "ps", "--filter", f"label=com.docker.compose.project={args.project}", "-q"], text=True).split()
    containers = []
    if ids:
        raw = subprocess.check_output(["docker", "stats", "--no-stream", "--format", "{{json .}}", *ids], text=True)
        containers = [json.loads(line) for line in raw.splitlines()]
    memory = {}
    source = Path("/proc/meminfo")
    if source.exists():
        for line in source.read_text().splitlines():
            key, value = line.split(":", 1)
            if key in {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}:memory[key] = value.strip()
    health = json.loads(subprocess.check_output(["docker", "inspect", *ids], text=True)) if ids else []
    unhealthy = [item["Name"].lstrip("/") for item in health
                 if item["State"].get("OOMKilled") or item["State"].get("Health", {}).get("Status") == "unhealthy"]
    result = {"unix": time.time(), "disk_total": disk.total, "disk_free": disk.free,
              "memory": memory, "containers": containers, "unhealthy_or_oom": unhealthy,
              "disk_warning": disk.free < max(5 * 1024 ** 3, disk.total // 10)}
    print(json.dumps(result))
    return 1 if result["disk_warning"] or unhealthy or not ids else 0


if __name__ == "__main__":raise SystemExit(main())
