#!/usr/bin/env python3
"""Run C167 under the declared node cap and a cumulative-obligation guard.

This continuation command is intentionally separate from ``reproduce.py``.  The
main command reserves an implementation-independent worst case and may skip C167.
Here a wrapper stops before the actual campaign ceiling, so the negative control
can be attempted without risking an over-budget run.  UNKNOWN remains a valid
resource-exhaustion result; it is never converted into equivalence.
"""
from __future__ import annotations

import csv
import json
import os
import resource
import signal
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

import branch_producer  # noqa: E402
import order_domain  # noqa: E402
from make_large_cases import fanout_case  # noqa: E402
from producer import Rejected  # noqa: E402

CEILING = 100_000
CALL_GUARD = 14_000
ADDRESS_LIMIT = 2_500 * 1024 * 1024


class ObligationGuard(Exception):
    pass


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    resource.setrlimit(resource.RLIMIT_AS, (ADDRESS_LIMIT, ADDRESS_LIMIT))
    resource.setrlimit(resource.RLIMIT_CPU, (110, 115))
    if hasattr(os, "sched_getaffinity"):
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    signal.alarm(118)

    summary_path = ROOT / "results" / "final_reproduction.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    before_total = summary["resource_accounting"]["cumulative_obligations"]
    if before_total + CALL_GUARD + 1 > CEILING:
        raise SystemExit("insufficient cumulative obligation headroom")
    if summary["fanout_control"]["status"] not in {"not_run_budget_reserve", "unknown_resource_exhaustion"}:
        raise SystemExit("unexpected existing fanout state")
    if summary["fanout_control"]["status"] == "unknown_resource_exhaustion":
        print(json.dumps({"status": "ALREADY_COMPLETE"}, sort_keys=True))
        return

    original_solve = branch_producer.solve
    local_calls = 0

    def guarded_solve(*args: Any, **kwargs: Any) -> Any:
        nonlocal local_calls
        if local_calls >= CALL_GUARD:
            raise ObligationGuard("local producer-call guard")
        local_calls += 1
        return original_solve(*args, **kwargs)

    branch_producer.solve = guarded_solve
    started = time.process_time()
    status: dict[str, Any]
    try:
        proof = branch_producer.certify(fanout_case(), max_nodes=6000, max_facts=48)
    except Rejected as error:
        status = {
            "status": "unknown_resource_exhaustion",
            "case_id": "C167",
            "reason": str(error),
            "node_limit": 6000,
            "predicate_limit": 48,
            "producer_domain_calls": local_calls,
            "top_level_attempts": 1,
            "counted_solver_checker_obligations": local_calls + 1,
            "cpu_seconds": time.process_time() - started,
            "local_call_guard": CALL_GUARD,
        }
    except ObligationGuard as error:
        status = {
            "status": "unknown_obligation_guard",
            "case_id": "C167",
            "reason": str(error),
            "node_limit": 6000,
            "predicate_limit": 48,
            "producer_domain_calls": local_calls,
            "top_level_attempts": 1,
            "counted_solver_checker_obligations": local_calls + 1,
            "cpu_seconds": time.process_time() - started,
            "local_call_guard": CALL_GUARD,
        }
    else:
        status = {
            "status": "completed",
            "case_id": "C167",
            "nodes": len(proof["nodes"]),
            "verdict": proof["verdict"],
            "producer_domain_calls": local_calls,
            "top_level_attempts": 1,
            "counted_solver_checker_obligations": local_calls + 1,
            "cpu_seconds": time.process_time() - started,
            "local_call_guard": CALL_GUARD,
        }

    new_total = before_total + status["counted_solver_checker_obligations"]
    if new_total > CEILING:
        raise AssertionError("cumulative obligation ceiling exceeded")
    summary["fanout_control"] = status
    accounting = summary["resource_accounting"]
    accounting["new_obligations"] += status["counted_solver_checker_obligations"]
    accounting["cumulative_obligations"] = new_total
    accounting["remaining_obligations"] = CEILING - new_total
    resources = summary["resources"]
    resources["continuation_fanout_cpu_seconds"] = status["cpu_seconds"]
    resources["continuation_fanout_peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    resources["process_cpu_seconds_including_continuation"] = resources["process_cpu_seconds"] + status["cpu_seconds"]
    resources["peak_rss_kib_including_continuation"] = max(
        resources["peak_rss_kib"], resources["continuation_fanout_peak_rss_kib"]
    )

    write_json(ROOT / "results" / "fanout_control.json", status)
    write_json(summary_path, summary)

    csv_path = ROOT / "results" / "resource_accounting.csv"
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    for row in rows:
        if row["phase"] == "final_C167_default_cap_attempt":
            row.update(
                {
                    "producer_solver_calls": str(status["producer_domain_calls"]),
                    "replayer_solver_calls": "0",
                    "other_checker_or_mutation_obligations": "1",
                    "counted_obligations": str(status["counted_solver_checker_obligations"]),
                    "cpu_seconds": str(status["cpu_seconds"]),
                    "evidence_note": status["status"],
                }
            )
            break
    else:
        raise AssertionError("resource accounting row absent")
    fields = list(rows[0])
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    signal.alarm(0)
    print(json.dumps({
        "status": status["status"],
        "producer_domain_calls": status["producer_domain_calls"],
        "cumulative_obligations": new_total,
        "remaining_obligations": CEILING - new_total,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
