#!/usr/bin/env python3
"""Local-only capacity measurements. Never opens a database or calls Gemini.

Run ``--workload api`` and ``--workload worker`` inside the deployment image
with a prepared, read-only /models volume. Use ``--containers ID ...`` outside
Docker to sample the complete running stack while its real E2E test executes.
The JSON contains resource counters and synthetic fixture checks, not documents.
Synthetic exec workloads add model processes: keep the actual job queue idle
while they run. Use the sampler alone during real API/browser E2E verification.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def counters():
    result = {"process_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss *
              (1 if sys.platform == "darwin" else 1024)}
    for name in ("memory.current", "memory.peak", "memory.max", "memory.events", "cpu.stat"):
        path = Path("/sys/fs/cgroup") / name
        if path.is_file():
            raw = path.read_text().strip()
            result[name] = int(raw) if raw.isdigit() else raw
    return result


def workload(role, rounds, hold_seconds):
    # Explicitly disallow accidental online model downloads/provider generation.
    if os.getenv("HF_HUB_OFFLINE") != "1":
        raise SystemExit("capacity workload requires HF_HUB_OFFLINE=1")
    started = time.monotonic()
    print(json.dumps({"role": role, "phase": "loading_cpu_runtime"}), flush=True)
    import torch
    torch.set_num_threads(1)
    from services.embedding_service import generate_embeddings
    fixture = "The fictional Aster Harbor equipment allowance is 83 credits for 17 days."
    results = {"role": role, "platform": platform.platform(), "machine": platform.machine(),
               "python": platform.python_version(), "torch": torch.__version__,
               "cuda_available": torch.cuda.is_available(), "rounds": rounds}
    embedding_round_seconds = []
    for _ in range(rounds):
        round_started = time.monotonic()
        vectors = generate_embeddings([fixture] * 8)
        embedding_round_seconds.append(round(time.monotonic() - round_started, 3))
        if tuple(vectors.shape) != (8, 384):
            raise RuntimeError("unexpected embedding dimensions")
    print(json.dumps({"role": role, "phase": "embedding_ready", **counters()}), flush=True)
    results["embedding_shape"] = list(vectors.shape)
    results["embedding_round_seconds"] = embedding_round_seconds
    if role == "api":
        from services.reranker_service import get_reranker
        scores = get_reranker().predict([("What is the allowance?", fixture)] * 10)
        if len(scores) != 10 or not all(math.isfinite(float(value)) for value in scores):
            raise RuntimeError("invalid reranker scores")
        results["reranked_candidates"] = len(scores)
        warm_started = time.monotonic()
        generate_embeddings([fixture] * 8)
        warm_scores = get_reranker().predict([("What is the allowance?", fixture)] * 10)
        if len(warm_scores) != 10 or not all(math.isfinite(float(value)) for value in warm_scores):
            raise RuntimeError("warm reranker output differs")
        results["warm_work_seconds"] = round(time.monotonic() - warm_started, 3)
    else:
        import pymupdf
        from services.ocr_service import extract_pages, OCROptions
        # Make an image-only synthetic PDF at runtime; no private fixture is copied.
        source = pymupdf.open()
        page = source.new_page()
        page.insert_text((60, 90), fixture, fontsize=18)
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
        scanned = pymupdf.open()
        scanned.new_page(width=page.rect.width, height=page.rect.height).insert_image(
            page.rect, stream=pixmap.tobytes("png"))
        with tempfile.TemporaryDirectory(prefix="rag-capacity-") as directory:
            pdf = Path(directory) / "synthetic-capacity.pdf"
            scanned.save(pdf)
            pages = extract_pages(pdf, options=OCROptions(max_pages=2))
            warm_started = time.monotonic()
            warm_pages = extract_pages(pdf, options=OCROptions(max_pages=2))
            generate_embeddings([fixture] * 8)
            results["warm_work_seconds"] = round(time.monotonic() - warm_started, 3)
        scanned.close()
        source.close()
        if (len(pages) != 1 or pages[0]["method"] == "native" or "83" not in pages[0]["text"]
                or len(warm_pages) != 1 or "83" not in warm_pages[0]["text"]):
            raise RuntimeError("real local OCR did not recover the synthetic fact")
        results["ocr_pages"] = len(pages)
        results["warm_ocr_pages"] = len(warm_pages)
        results["ocr_method"] = pages[0]["method"]
    results["work_seconds"] = round(time.monotonic() - started, 3)
    results.update(counters())
    print(json.dumps(results), flush=True)
    # Keep model copies resident while the other role and full stack are measured.
    time.sleep(hold_seconds)
    print(json.dumps({"role": role, "final": counters()}), flush=True)


def sample(containers, duration, output):
    path = Path(output)
    # Reserve the identity before sampling; never overwrite an earlier run.
    stream = path.open("x")
    path.chmod(0o600)
    samples = []
    started = time.monotonic()
    data = {"status": "running", "samples": samples, "inspections": []}
    def checkpoint():
        stream.seek(0)
        json.dump(data, stream, indent=2)
        stream.write("\n")
        stream.truncate()
        stream.flush()
    with stream:
        checkpoint()
        while time.monotonic() - started < duration:
            try:
                result = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{json .}}",
                                         *containers], text=True, capture_output=True, check=False, timeout=15)
            except subprocess.TimeoutExpired:
                result = subprocess.CompletedProcess([], 124, "", "Docker stats probe timed out")
            item = {"elapsed_seconds": round(time.monotonic() - started, 3)}
            if result.returncode:
                # Recreating a container can invalidate stats' resolved ID. Keep
                # the interruption visible; never replace missing data with zero.
                item["probe_error"] = {"return_code": result.returncode,
                                       "message": result.stderr.strip()[:300]}
            else:
                item["containers"] = [json.loads(line) for line in result.stdout.splitlines() if line]
            samples.append(item)
            checkpoint()
            time.sleep(1)
        for container in containers:
            # Select only lifecycle/resource fields; never emit Config.Env or secrets.
            state = json.loads(subprocess.check_output(
                ["docker", "inspect", "--format", "{{json .State}}", container], text=True, timeout=10))
            limits = json.loads(subprocess.check_output(
                ["docker", "inspect", "--format", "{{json .HostConfig}}", container], text=True, timeout=10))
            raw_cgroup = subprocess.check_output(
                ["docker", "exec", container, "cat", "/sys/fs/cgroup/memory.current",
                 "/sys/fs/cgroup/memory.peak", "/sys/fs/cgroup/memory.events", "/sys/fs/cgroup/cpu.stat"],
                text=True, timeout=10).splitlines()
            cgroup = {"memory_current_bytes": int(raw_cgroup[0]), "memory_peak_bytes": int(raw_cgroup[1]),
                      **{key: int(value) for key, value in (line.split() for line in raw_cgroup[2:])}}
            data["inspections"].append({"container": container, "state": state,
                                        "memory_limit_bytes": limits["Memory"],
                                        "nano_cpus": limits["NanoCpus"],
                                        "cpuset_cpus": limits["CpusetCpus"],
                                        "memory_swap_bytes": limits["MemorySwap"], "cgroup": cgroup})
        data["probe_errors"] = sum("probe_error" in item for item in samples)
        data["status"] = "complete_with_probe_errors" if data["probe_errors"] else "complete"
        data["duration_seconds"] = round(time.monotonic() - started, 3)
        checkpoint()
    print(json.dumps({"output": str(path), "samples": len(samples),
                      "probe_errors": data["probe_errors"],
                      "oom_killed": any(item["state"]["OOMKilled"] for item in data["inspections"])}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workload", choices=("api", "worker"))
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--hold-seconds", type=int, default=30)
    parser.add_argument("--containers", nargs="+")
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--output")
    args = parser.parse_args()
    if not 1 <= args.rounds <= 20 or not 0 <= args.hold_seconds <= 600 or not 1 <= args.duration <= 600:
        parser.error("workload duration or rounds out of bounds")
    if args.workload and not args.containers:
        workload(args.workload, args.rounds, args.hold_seconds)
    elif args.containers and args.output and not args.workload:
        sample(args.containers, args.duration, args.output)
    else:
        parser.error("select workload, or containers with an exclusive output path")


if __name__ == "__main__":
    main()
