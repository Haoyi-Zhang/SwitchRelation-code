"""Budget-aware final audit of the retained bounded research artifact.

This script intentionally does not regenerate certificates or rerun C167.  It
uses the remaining campaign allowance to (1) rematerialize all case schemas,
(2) rerun the constructive full-abstraction audit, (3) cross-check fresh region
instances, (4) replay C001--C165, and (5) repeat the mutation suite.  C166 is
covered by retained prior replay evidence and by independent direct concrete
checks here; a fresh full C166 replay would exceed the cumulative 100,000
obligation ceiling.

Direct concrete executions are recorded separately from solver/mutation/checker
obligations, exactly as in the frozen accounting rule.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import os
import random
import resource
import sys
import time
from pathlib import Path
from typing import Any, Iterable

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import branch_replay  # noqa: E402
import check_full_abstraction  # noqa: E402
import check_mutations  # noqa: E402
import check_regions  # noqa: E402
import make_cases  # noqa: E402
import make_large_cases  # noqa: E402
import order_domain  # noqa: E402
import producer  # noqa: E402
import replay  # noqa: E402

OBLIGATION_CEILING = 100_000
INHERITED_OBLIGATIONS = 91_087
EXPECTED_REPLAY_LAST = 165
REGION_INSTANCES = 320
REGION_SEED = 20260916


def _set_limits() -> None:
    """Apply the declared one-process memory guard where supported."""
    try:
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    except (AttributeError, OSError):
        pass
    limit = 2_500 * 1024 * 1024
    try:
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    except (AttributeError, OSError, ValueError):
        pass


def _load_cases() -> list[dict[str, Any]]:
    paths = sorted((ROOT / "cases").glob("C*.json"))
    cases = [branch_replay.load(path) for path in paths]
    expected_ids = [f"C{index:03d}" for index in range(1, 168)]
    if [case["id"] for case in cases] != expected_ids:
        raise AssertionError("case identifier sequence")
    return cases


def _rematerialization_audit(cases: list[dict[str, Any]]) -> dict[str, Any]:
    generated = make_cases.build() + make_large_cases.build() + [make_large_cases.fanout_case()]
    if len(generated) != len(cases):
        raise AssertionError("generated case count")
    for actual, expected in zip(cases, generated):
        if actual != expected:
            raise AssertionError(f"case materialization mismatch: {actual.get('id')}")
    return {
        "status": "pass",
        "case_count": len(cases),
        "first": cases[0]["id"],
        "last": cases[-1]["id"],
        "checker_obligations": len(cases),
        "comparison": "parsed JSON objects exactly equal deterministic generators",
    }


def _replay_prefix(cases: list[dict[str, Any]]) -> dict[str, Any]:
    rows = {
        row["id"]: row
        for row in csv.DictReader((ROOT / "results" / "branch_cases.csv").open(encoding="utf-8"))
    }
    before = branch_replay.DOMAIN_CALLS
    totals = {
        "nodes": 0,
        "leaves": 0,
        "closed_branches": 0,
        "equivalent_cases": 0,
        "different_cases": 0,
    }
    checked: list[str] = []
    start = time.process_time()
    for case in cases[:EXPECTED_REPLAY_LAST]:
        proof = branch_replay.load(ROOT / "certificates" / "branch" / f"{case['id']}.json")
        result = branch_replay.check(case, proof)
        row = rows[case["id"]]
        for key in ("verdict", "least_input"):
            expected: Any = row[key]
            if key == "least_input":
                expected = json.loads(expected) if expected != "null" else None
            if result[key] != expected:
                raise AssertionError(f"retained summary mismatch {case['id']} {key}")
        if result["nodes"] != int(row["nodes"]) or result["leaves"] != int(row["leaves"]):
            raise AssertionError(f"retained count mismatch {case['id']}")
        if result["closed_branches"] != int(row["closed_branches"]):
            raise AssertionError(f"retained closed-branch mismatch {case['id']}")
        totals["nodes"] += result["nodes"]
        totals["leaves"] += result["leaves"]
        totals["closed_branches"] += result["closed_branches"]
        totals[result["verdict"] + "_cases"] += 1
        checked.append(case["id"])
    calls = branch_replay.DOMAIN_CALLS - before
    expected_calls = sum(int(rows[case_id]["replayer_domain_calls"]) for case_id in checked)
    if calls != expected_calls:
        raise AssertionError(f"replay call count: {calls} != {expected_calls}")
    cpu = time.process_time() - start
    return {
        "status": "pass",
        "first": checked[0],
        "last": checked[-1],
        "certificates_replayed": len(checked),
        "excluded_from_fresh_replay": "C166",
        "exclusion_reason": "a full fresh C166 replay would exceed the cumulative obligation ceiling",
        "replayer_domain_calls": calls,
        "top_level_checker_obligations": len(checked),
        "counted_solver_checker_obligations": calls + len(checked),
        "cpu_seconds": cpu,
        **totals,
    }


def _sample_vectors(width: int, seed: int, count: int = 16) -> list[tuple[int, ...]]:
    if width == 0:
        return [()]
    base = [
        tuple(0 for _ in range(width)),
        tuple(1 for _ in range(width)),
        tuple(255 for _ in range(width)),
        tuple(128 for _ in range(width)),
        tuple((0 if index % 2 == 0 else 255) for index in range(width)),
        tuple((255 if index % 2 == 0 else 0) for index in range(width)),
        tuple(index % 256 for index in range(width)),
        tuple((255 - index) % 256 for index in range(width)),
    ]
    rng = random.Random(seed)
    while len(base) < count:
        base.append(tuple(rng.randrange(256) for _ in range(width)))
    unique: list[tuple[int, ...]] = []
    seen: set[tuple[int, ...]] = set()
    for values in base:
        if values not in seen:
            unique.append(values)
            seen.add(values)
    return unique


def _triple_check(case: dict[str, Any], values: tuple[int, ...], program_key: str) -> list[Any]:
    program = case[program_key]
    direct = replay.interpret(case, values, program)
    list_backend = producer.Machine(case, values, strings=False).run(program)
    string_backend = producer.Machine(case, values, strings=True).run(program)
    if direct != list_backend or direct != string_backend:
        raise AssertionError(
            f"concrete interpreter mismatch {case['id']} {program_key} {values}: "
            f"{direct!r} {list_backend!r} {string_backend!r}"
        )
    return direct


def _direct_concrete_audit(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Independent concrete checks that consume no regional-solver obligation."""
    assignment_checks = 0
    program_executions = 0
    leaf_minima = 0
    exhaustive_one_byte_assignments = 0
    exhaustive_two_byte_difference_assignments = 0
    sampled_assignments = 0

    # Recompute every stored leaf outcome at its stored regional minimum with
    # both concrete backends and the independently structured direct interpreter.
    for case in cases[:166]:
        proof = branch_replay.load(ROOT / "certificates" / "branch" / f"{case['id']}.json")
        for node in proof["nodes"]:
            if node.get("kind") != "leaf":
                continue
            values = tuple(node["minimum"])
            left = _triple_check(case, values, "reference")
            right = _triple_check(case, values, "candidate")
            program_executions += 6
            assignment_checks += 1
            leaf_minima += 1
            if left != node["left"] or right != node["right"]:
                raise AssertionError(f"leaf minimum outcome mismatch {case['id']} {values}")

    # Exhaust every one-byte input case, including all correct and intentionally
    # wrong candidates, through three independently structured concrete paths.
    for case in cases:
        if len(case["variables"]) != 1:
            continue
        for value in range(256):
            values = (value,)
            _triple_check(case, values, "reference")
            _triple_check(case, values, "candidate")
            assignment_checks += 1
            exhaustive_one_byte_assignments += 1
            program_executions += 6

    # For all two-byte cases whose retained verdict is different, exhaust the
    # full 65,536 assignments and recompute both least exact and least acceptance
    # disagreements with the independent direct interpreter.
    summaries = {
        row["id"]: row
        for row in csv.DictReader((ROOT / "results" / "branch_cases.csv").open(encoding="utf-8"))
    }
    two_byte_cases = []
    for case in cases[:166]:
        row = summaries[case["id"]]
        if len(case["variables"]) != 2 or row["verdict"] != "different":
            continue
        least = None
        acceptance_least = None
        for values in itertools.product(range(256), repeat=2):
            left = replay.interpret(case, values, case["reference"])
            right = replay.interpret(case, values, case["candidate"])
            program_executions += 2
            assignment_checks += 1
            exhaustive_two_byte_difference_assignments += 1
            if left != right and least is None:
                least = list(values)
            if (left[0] == "accept") != (right[0] == "accept") and acceptance_least is None:
                acceptance_least = list(values)
        expected_least = json.loads(row["least_input"])
        proof = branch_replay.load(ROOT / "certificates" / "branch" / f"{case['id']}.json")
        if least != expected_least or acceptance_least != proof["feasibility"]["least_input"]:
            raise AssertionError(f"exhaustive witness mismatch {case['id']}")
        two_byte_cases.append(case["id"])

    # Exercise every case, including C166 and the uncertified C167 cap control,
    # on deterministic boundary and seeded samples through all three concrete
    # implementations.  Sampling C167 is not promoted to an equivalence verdict.
    for ordinal, case in enumerate(cases, 1):
        for values in _sample_vectors(len(case["variables"]), 20260916 + ordinal):
            _triple_check(case, values, "reference")
            _triple_check(case, values, "candidate")
            assignment_checks += 1
            sampled_assignments += 1
            program_executions += 6

    return {
        "status": "pass",
        "assignment_checks": assignment_checks,
        "program_executions": program_executions,
        "leaf_minima_recomputed": leaf_minima,
        "exhaustive_one_byte_assignments": exhaustive_one_byte_assignments,
        "exhaustive_two_byte_difference_cases": two_byte_cases,
        "exhaustive_two_byte_difference_assignments": exhaustive_two_byte_difference_assignments,
        "deterministic_sample_assignments": sampled_assignments,
        "includes_uncertified_C167_samples": True,
        "scope": "direct concrete consistency checks; no full-domain claim for sampled multi-byte cases",
        "counted_solver_mutation_checker_obligations": 0,
    }


def run() -> dict[str, Any]:
    _set_limits()
    started = time.monotonic()
    cpu_started = time.process_time()
    cases = _load_cases()

    materialization = _rematerialization_audit(cases)
    full_abstraction = check_full_abstraction.run()
    region_crosscheck = check_regions.run(REGION_INSTANCES, REGION_SEED)
    prefix_replay = _replay_prefix(cases)

    c001 = cases[0]
    p001 = branch_replay.load(ROOT / "certificates" / "branch" / "C001.json")
    mutation = check_mutations.run(c001, p001)
    direct = _direct_concrete_audit(cases)

    counted = (
        materialization["checker_obligations"]
        + full_abstraction["pair_checks_total"]
        + region_crosscheck["counted_solver_checker_obligations"]
        + prefix_replay["counted_solver_checker_obligations"]
        + mutation["counted_solver_mutation_checker_obligations"]
    )
    cumulative = INHERITED_OBLIGATIONS + counted
    if cumulative > OBLIGATION_CEILING:
        raise AssertionError(f"campaign ceiling exceeded: {cumulative}")

    result = {
        "status": "pass",
        "scope": "budget-aware continuation audit; retained C166 full replay is not rerun",
        "case_materialization": materialization,
        "full_abstraction_witness_audit": full_abstraction,
        "fresh_region_solver_crosscheck": region_crosscheck,
        "fresh_certificate_replay": prefix_replay,
        "fresh_mutation_suite": mutation,
        "direct_concrete_audit": direct,
        "resource_accounting": {
            "inherited_counted_obligations": INHERITED_OBLIGATIONS,
            "new_counted_obligations": counted,
            "cumulative_counted_obligations": cumulative,
            "obligation_ceiling": OBLIGATION_CEILING,
            "remaining_obligations": OBLIGATION_CEILING - cumulative,
            "new_direct_concrete_assignment_checks": direct["assignment_checks"],
            "counting_rule": (
                "Direct concrete semantic assignments are reported separately. "
                "Case rematerializations, state-pair audits, region calls, top-level "
                "certificate checks, and mutation attempts are counted; repeated runs "
                "are not deduplicated."
            ),
        },
        "resources": {
            "workers": 1,
            "wall_seconds": time.monotonic() - started,
            "process_cpu_seconds": time.process_time() - cpu_started,
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        },
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "final_continuation_audit.json")
    args = parser.parse_args()
    result = run()
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
