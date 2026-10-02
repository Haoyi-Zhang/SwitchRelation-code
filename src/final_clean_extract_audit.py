"""Final budget-closing replay from a clean project extraction.

The retained campaign had 305 solver/mutation/checker obligations available.
This audit spends exactly 304 of them: 299 region calls plus five top-level
certificate checks.  The selected certificates cover both verdicts, one- and
two-byte mutation witnesses, tail erasure/exposure, high-dimensional path
feasibility, and an eight-byte equivalent comparison.  It neither regenerates
certificates nor runs the intentionally resource-exhausted C167 case.

Run this script at most once for the retained final campaign.  Static packaging
checks and document compilation are outside the scientific-obligation count.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import resource
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import branch_replay  # noqa: E402

OBLIGATION_CEILING = 100_000
INHERITED_OBLIGATIONS = 99_695
SELECTED: tuple[tuple[str, int, str], ...] = (
    ("C061", 1, "equivalent read-only tail erasure"),
    ("C062", 4, "different result after erased tail becomes observable"),
    ("C065", 34, "different signed-order simplification"),
    ("C162", 97, "32-byte different path-feasibility result"),
    ("C163", 163, "eight-byte equivalent long comparison"),
)
EXPECTED_REGION_CALLS = 299
EXPECTED_TOP_LEVEL_CHECKS = 5
EXPECTED_NEW_OBLIGATIONS = 304
EXPECTED_CUMULATIVE_OBLIGATIONS = 99_999


def fail(message: str) -> None:
    raise RuntimeError(message)


def set_limits() -> dict[str, Any]:
    """Apply the declared single-worker CPU-affinity and address-space guard."""
    affinity_applied = False
    memory_limit_applied = False
    try:
        available = os.sched_getaffinity(0)
        os.sched_setaffinity(0, {min(available)})
        affinity_applied = True
    except (AttributeError, OSError, ValueError):
        pass
    limit = 2_500 * 1024 * 1024
    try:
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        memory_limit_applied = True
    except (AttributeError, OSError, ValueError):
        pass
    return {
        "workers": 1,
        "cpu_affinity_guard_applied": affinity_applied,
        "address_space_limit_bytes": limit if memory_limit_applied else None,
    }


def load_summary_rows() -> dict[str, dict[str, str]]:
    path = ROOT / "results" / "branch_cases.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        rows = {row["id"]: row for row in csv.DictReader(handle)}
    missing = [case_id for case_id, _, _ in SELECTED if case_id not in rows]
    if missing:
        fail(f"missing retained summary rows: {missing}")
    return rows


def parse_optional_json(value: str) -> Any:
    return None if value == "null" else json.loads(value)


def validate_result(case_id: str, row: dict[str, str], result: dict[str, Any]) -> None:
    expected = {
        "id": case_id,
        "nodes": int(row["nodes"]),
        "leaves": int(row["leaves"]),
        "closed_branches": int(row["closed_branches"]),
        "max_predicates": int(row["max_predicates"]),
        "verdict": row["verdict"],
        "least_input": parse_optional_json(row["least_input"]),
    }
    for key, value in expected.items():
        if result.get(key) != value:
            fail(f"{case_id}: replayed {key}={result.get(key)!r}, expected {value!r}")
    expected_feasibility = {
        "reference": row["reference_feasibility"],
        "candidate": row["candidate_feasibility"],
        "verdict": row["feasibility_verdict"],
        "least_input": None,
    }
    # The CSV stores the result-divergence witness but not a separate
    # feasibility witness.  Bind the remaining fields here and compare the
    # complete object to the certificate itself below.
    actual_feasibility = result.get("feasibility")
    if not isinstance(actual_feasibility, dict):
        fail(f"{case_id}: missing feasibility result")
    for key in ("reference", "candidate", "verdict"):
        if actual_feasibility.get(key) != expected_feasibility[key]:
            fail(
                f"{case_id}: replayed feasibility {key}={actual_feasibility.get(key)!r}, "
                f"expected {expected_feasibility[key]!r}"
            )


def run() -> dict[str, Any]:
    limits = set_limits()
    rows = load_summary_rows()
    branch_replay.DOMAIN_CALLS = 0
    started_wall = time.time()
    started_cpu = time.process_time()
    records: list[dict[str, Any]] = []

    for case_id, expected_calls, rationale in SELECTED:
        row = rows[case_id]
        retained_calls = int(row["replayer_domain_calls"])
        if retained_calls != expected_calls:
            fail(
                f"{case_id}: frozen expected calls {expected_calls}, "
                f"retained summary reports {retained_calls}"
            )
        case_path = ROOT / "cases" / f"{case_id}.json"
        certificate_path = ROOT / "certificates" / "branch" / f"{case_id}.json"
        if not case_path.is_file() or not certificate_path.is_file():
            fail(f"{case_id}: case or certificate missing")
        case = branch_replay.load(case_path)
        proof = branch_replay.load(certificate_path)
        if case.get("id") != case_id:
            fail(f"{case_id}: case identifier mismatch")

        before_calls = branch_replay.DOMAIN_CALLS
        case_cpu_start = time.process_time()
        result = branch_replay.check(case, proof)
        case_cpu = time.process_time() - case_cpu_start
        calls = branch_replay.DOMAIN_CALLS - before_calls
        if calls != expected_calls:
            fail(f"{case_id}: fresh region-call count {calls}, expected {expected_calls}")
        validate_result(case_id, row, result)
        if proof.get("feasibility") != result["feasibility"]:
            fail(f"{case_id}: certificate feasibility summary mismatch")

        records.append(
            {
                "id": case_id,
                "selection_rationale": rationale,
                "variables": len(case["variables"]),
                "verdict": result["verdict"],
                "least_input": result["least_input"],
                "feasibility": result["feasibility"],
                "nodes": result["nodes"],
                "leaves": result["leaves"],
                "closed_branches": result["closed_branches"],
                "max_predicates": result["max_predicates"],
                "replayer_region_calls": calls,
                "top_level_checker_obligations": 1,
                "counted_obligations": calls + 1,
                "cpu_seconds": case_cpu,
            }
        )

    total_calls = branch_replay.DOMAIN_CALLS
    total_checks = len(records)
    new_obligations = total_calls + total_checks
    cumulative = INHERITED_OBLIGATIONS + new_obligations
    remaining = OBLIGATION_CEILING - cumulative
    if total_calls != EXPECTED_REGION_CALLS:
        fail(f"fresh region-call total {total_calls}, expected {EXPECTED_REGION_CALLS}")
    if total_checks != EXPECTED_TOP_LEVEL_CHECKS:
        fail(f"top-level check total {total_checks}, expected {EXPECTED_TOP_LEVEL_CHECKS}")
    if new_obligations != EXPECTED_NEW_OBLIGATIONS:
        fail(f"new obligation total {new_obligations}, expected {EXPECTED_NEW_OBLIGATIONS}")
    if cumulative != EXPECTED_CUMULATIVE_OBLIGATIONS or remaining != 1:
        fail(f"campaign accounting mismatch: cumulative={cumulative}, remaining={remaining}")

    usage = resource.getrusage(resource.RUSAGE_SELF)
    return {
        "status": "pass",
        "scope": "retained-certificate replay from a clean extracted candidate project",
        "execution_date": time.strftime("%Y-%m-%d", time.gmtime(started_wall)),
        "selection": [case_id for case_id, _, _ in SELECTED],
        "selection_policy": (
            "predeclared stratified boundary set spanning both verdicts, tail-view mutation, "
            "signed-order mutation, 32-byte feasibility divergence, and multi-byte equivalence"
        ),
        "certificates_replayed": total_checks,
        "replayer_region_calls": total_calls,
        "top_level_checker_obligations": total_checks,
        "new_counted_obligations": new_obligations,
        "inherited_counted_obligations": INHERITED_OBLIGATIONS,
        "cumulative_counted_obligations": cumulative,
        "obligation_ceiling": OBLIGATION_CEILING,
        "remaining_obligations": remaining,
        "direct_concrete_evaluations_added": 0,
        "cpu_seconds": time.process_time() - started_cpu,
        "wall_seconds": time.time() - started_wall,
        "peak_rss_kib": usage.ru_maxrss,
        "limits": limits,
        "cases": records,
        "nonclaims": [
            "This stratified replay is not a second full-campaign reproduction.",
            "C166 retains its earlier complete replay evidence and is not replayed here.",
            "C167 remains an explicit resource-exhaustion result rather than a semantic verdict.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "results" / "final_clean_extract_audit.json",
    )
    args = parser.parse_args()
    try:
        result = run()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(args.output)
        print(json.dumps(result, sort_keys=True))
    except (KeyError, OSError, RuntimeError, TypeError, ValueError, RecursionError) as error:
        raise SystemExit(f"FINAL_CLEAN_EXTRACT_AUDIT_FAILED: {error}")


if __name__ == "__main__":
    main()
