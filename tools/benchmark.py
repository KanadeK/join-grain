"""Synthetic distinct-key workload; checks counts and cleans all inputs."""

import argparse
import csv
import json
import tempfile
import time
import tracemalloc
from pathlib import Path

from join_grain.core import audit

parser = argparse.ArgumentParser()
parser.add_argument("--rows", type=int, default=100000)
args = parser.parse_args()
if args.rows < 1:
    parser.error("rows must be positive")
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    for name in ("left", "right"):
        with (root / f"{name}.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["id"])
            writer.writerows((str(i),) for i in range(args.rows))
    tracemalloc.start()
    start = time.perf_counter()
    report = audit(root / "left.csv", root / "right.csv", left_keys=("id",), expect="one-to-one")
    elapsed = time.perf_counter() - start
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert report["ok"] and all(n == args.rows for n in report["predicted_rows"].values())
    print(
        json.dumps(
            {
                "rows_per_side": args.rows,
                "elapsed_seconds": round(elapsed, 3),
                "peak_python_traced_bytes": peak,
                "note": "excludes SQLite C allocations and OS cache",
            }
        )
    )
