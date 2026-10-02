#!/usr/bin/env python3
"""Run a new, isolated bounded campaign without modifying the artifact tree.

The checked-in ``results/`` and ``certificates/`` directories are retained
historical evidence.  This command requires an external output directory,
re-reads every generated certificate before same-process replay, runs one
independent CLI smoke, snapshots the exact static inputs/evidence used, and
refuses to replace an existing campaign directory.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
SELF_ACCEPTANCE_RECORD = Path("results/isolated_campaign_acceptance.json")
sys.path.insert(0, str(SRC))

import branch_replay  # noqa: E402
import order_domain  # noqa: E402
from branch_producer import certify as branch_certify  # noqa: E402
from check_full_abstraction import run as check_full_abstraction  # noqa: E402
from check_mutations import run as check_mutations  # noqa: E402
from check_regions import run as check_regions  # noqa: E402
from make_cases import build as build_small  # noqa: E402
from make_large_cases import build as build_large, fanout_case  # noqa: E402
from primitive_oracle import run as primitive_oracle  # noqa: E402
from producer import Rejected  # noqa: E402
from replay import load  # noqa: E402

ADDRESS_LIMIT_BYTES = 2_500 * 1024 * 1024
CPU_SOFT_SECONDS = 110
CPU_HARD_SECONDS = 115
WALL_SECONDS = 118


def json_text(value: Any, *, compact: bool = False) -> str:
    if compact:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def configure_resources() -> dict[str, Any]:
    resource.setrlimit(resource.RLIMIT_AS, (ADDRESS_LIMIT_BYTES, ADDRESS_LIMIT_BYTES))
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SOFT_SECONDS, CPU_HARD_SECONDS))
    if hasattr(os, "sched_getaffinity"):
        available = os.sched_getaffinity(0)
        chosen = min(available)
        os.sched_setaffinity(0, {chosen})
        affinity = sorted(os.sched_getaffinity(0))
    else:
        affinity = []
    signal.alarm(WALL_SECONDS)
    return {
        "workers": 1,
        "cpu_affinity": affinity,
        "address_space_limit_bytes": ADDRESS_LIMIT_BYTES,
        "cpu_soft_limit_seconds": CPU_SOFT_SECONDS,
        "cpu_hard_limit_seconds": CPU_HARD_SECONDS,
        "wall_alarm_seconds": WALL_SECONDS,
    }


def _artifact_files() -> list[Path]:
    """Return the read-only scientific input/evidence tree for integrity hashing.

    The acceptance record produced *after* a successful isolated run is excluded
    from its own input digest. Every other retained file is included.
    """
    return [
        path for path in sorted(ROOT.rglob("*"))
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
        and path.relative_to(ROOT) != SELF_ACCEPTANCE_RECORD
    ]


def tree_digest(paths: Iterable[Path]) -> tuple[str, int, int]:
    digest = hashlib.sha256()
    count = 0
    total = 0
    for path in paths:
        relative = path.relative_to(ROOT).as_posix().encode("utf-8")
        data = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
        count += 1
        total += len(data)
    return digest.hexdigest(), count, total


def require_external_output(path: Path) -> None:
    resolved = path.resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("--output-dir must be outside the read-only artifact root")
    if resolved.exists():
        raise ValueError("--output-dir already exists; campaigns are immutable")


def regenerated_cases() -> list[dict[str, Any]]:
    cases = build_small() + build_large() + [fanout_case()]
    expected = [f"C{index:03d}" for index in range(1, len(cases) + 1)]
    if [case["id"] for case in cases] != expected:
        raise AssertionError("generated case identifiers are not contiguous")
    return cases


def compare_materialized_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    paths = sorted((ROOT / "cases").glob("C*.json"))
    if len(paths) != len(cases):
        raise AssertionError("materialized/generated case count mismatch")
    mismatch = [case["id"] for case, path in zip(cases, paths) if load(path) != case]
    if mismatch:
        raise AssertionError("case regeneration mismatch: " + ",".join(mismatch))
    return {
        "status": "pass",
        "case_count": len(cases),
        "first": cases[0]["id"],
        "last": cases[-1]["id"],
        "checker_obligations": len(cases),
        "comparison": "parsed JSON objects exactly equal deterministic generators",
    }


def produce_and_replay(
    cases: list[dict[str, Any]], certificate_dir: Path
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, Any]]:
    certificate_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    retained: dict[str, dict[str, Any]] = {}
    producer_before = order_domain.SOLVE_CALLS
    replay_before = branch_replay.DOMAIN_CALLS
    started = time.process_time()
    for generated in cases:
        if generated["id"] == "C167":
            continue
        # Both the statement and proof consumed by the replayer are serialized
        # files.  Replay remains in this process; process isolation is not claimed.
        case = load(ROOT / "cases" / f"{generated['id']}.json")
        p0 = order_domain.SOLVE_CALLS
        producer_start = time.process_time()
        proof = branch_certify(case, max_nodes=6000, max_facts=48)
        produced_cpu = time.process_time() - producer_start
        path = certificate_dir / f"{case['id']}.json"
        path.write_text(json_text(proof, compact=True), encoding="utf-8")
        serialized_proof = load(path)
        r0 = branch_replay.DOMAIN_CALLS
        replay_start = time.process_time()
        checked = branch_replay.check(case, serialized_proof)
        replay_cpu = time.process_time() - replay_start
        if checked["verdict"] != case["expected"]:
            raise AssertionError(f"expected label mismatch for {case['id']}")
        retained[case["id"]] = serialized_proof
        rows.append({
            "id": case["id"],
            "family": case["family"],
            "variables": len(case["variables"]),
            "verdict": checked["verdict"],
            "expected": case["expected"],
            "nodes": checked["nodes"],
            "leaves": checked["leaves"],
            "closed_branches": checked["closed_branches"],
            "max_predicates": checked["max_predicates"],
            "reference_feasibility": checked["feasibility"]["reference"],
            "candidate_feasibility": checked["feasibility"]["candidate"],
            "feasibility_verdict": checked["feasibility"]["verdict"],
            "least_input": json.dumps(checked["least_input"], separators=(",", ":")),
            "producer_domain_calls": order_domain.SOLVE_CALLS - p0,
            "replayer_domain_calls": branch_replay.DOMAIN_CALLS - r0,
            "replay_mode": "serialized_file_reread_same_process",
            "producer_cpu_seconds": produced_cpu,
            "replayer_cpu_seconds": replay_cpu,
            "certificate_bytes": path.stat().st_size,
        })
    producer_calls = order_domain.SOLVE_CALLS - producer_before
    replay_calls = branch_replay.DOMAIN_CALLS - replay_before
    summary = {
        "status": "pass",
        "certified_cases": len(rows),
        "first": rows[0]["id"],
        "last": rows[-1]["id"],
        "expected_labels_matched": len(rows),
        "producer_domain_calls": producer_calls,
        "replayer_domain_calls": replay_calls,
        "top_level_producer_checker_obligations": 2 * len(rows),
        "counted_solver_checker_obligations": producer_calls + replay_calls + 2 * len(rows),
        "nodes": sum(int(row["nodes"]) for row in rows),
        "leaves": sum(int(row["leaves"]) for row in rows),
        "closed_branches": sum(int(row["closed_branches"]) for row in rows),
        "different_cases": sum(row["verdict"] == "different" for row in rows),
        "equivalent_cases": sum(row["verdict"] == "equivalent" for row in rows),
        "cpu_seconds": time.process_time() - started,
        "certificate_bytes": sum(int(row["certificate_bytes"]) for row in rows),
        "replay_mode": "each generated certificate serialized, re-read, then replayed in the campaign process",
    }
    return rows, retained, summary


def select_mutation_case(
    cases: list[dict[str, Any]], proofs: dict[str, dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    by_id = {case["id"]: case for case in cases}
    for case_id in sorted(proofs):
        kinds = {node.get("kind") for node in proofs[case_id]["nodes"] if isinstance(node, dict)}
        if {"split", "leaf"} <= kinds:
            return by_id[case_id], proofs[case_id]
    raise AssertionError("no certificate contains split and leaf nodes")


def run_fanout(case: dict[str, Any]) -> dict[str, Any]:
    before = order_domain.SOLVE_CALLS
    started = time.process_time()
    try:
        proof = branch_certify(case, max_nodes=6000, max_facts=48)
    except Rejected as error:
        calls = order_domain.SOLVE_CALLS - before
        if str(error) != "branch node budget":
            raise
        return {
            "status": "unknown_resource_exhaustion",
            "case_id": case["id"],
            "schema_expected_field": case.get("expected"),
            "schema_expected_field_is_not_a_validated_verdict": True,
            "reason": str(error),
            "node_limit": 6000,
            "predicate_limit": 48,
            "producer_domain_calls": calls,
            "top_level_attempts": 1,
            "counted_solver_checker_obligations": calls + 1,
            "cpu_seconds": time.process_time() - started,
        }
    checked = branch_replay.check(case, proof)
    return {
        "status": "completed",
        "case_id": case["id"],
        "nodes": checked["nodes"],
        "verdict": checked["verdict"],
        "producer_domain_calls": order_domain.SOLVE_CALLS - before,
        "top_level_attempts": 1,
        "cpu_seconds": time.process_time() - started,
    }


def independent_cli_smoke(certificate_dir: Path) -> dict[str, Any]:
    command = [
        sys.executable,
        str(SRC / "branch_replay.py"),
        str(ROOT / "cases" / "C135.json"),
        str(certificate_dir / "C135.json"),
    ]
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        command, cwd=ROOT, env=env, capture_output=True, text=True,
        timeout=30, check=False,
    )
    if completed.returncode != 0:
        raise AssertionError("independent CLI smoke failed: " + completed.stderr[-2000:])
    result = json.loads(completed.stdout)
    if result.get("id") != "C135" or result.get("process_isolation") != "independent_cli_process":
        raise AssertionError("independent CLI smoke output")
    return {
        "status": "pass",
        "case_id": "C135",
        "process_mode": "independent_cli_process",
        "replayer_region_calls": result["replayer_region_calls"],
        "top_level_checker_obligations": result["top_level_checker_obligations"],
        "counted_obligations": result["counted_obligations"],
        "verdict": result["verdict"],
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise AssertionError("empty CSV")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def copy_inputs(stage: Path) -> None:
    """Snapshot every static artifact asset and all retained evidence.

    ``results/`` and ``certificates/`` are copied under retained evidence. All
    other artifact files/directories are copied under a complete static snapshot.
    The self-referential isolated acceptance record is deliberately omitted.
    """
    static_root = stage / "static-inputs" / "artifact"
    retained_root = stage / "retained-evidence" / "artifact"
    static_root.mkdir(parents=True)
    retained_root.mkdir(parents=True)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    for source in sorted(ROOT.iterdir()):
        if source.name in {"results", "certificates"}:
            continue
        destination = static_root / source.name
        if source.is_dir():
            shutil.copytree(source, destination, ignore=ignore)
        elif source.is_file():
            shutil.copy2(source, destination)
    shutil.copytree(ROOT / "results", retained_root / "results", ignore=ignore)
    self_record = retained_root / SELF_ACCEPTANCE_RECORD
    if self_record.exists():
        self_record.unlink()
    shutil.copytree(ROOT / "certificates", retained_root / "certificates", ignore=ignore)


def platform_record(limits: dict[str, Any]) -> dict[str, Any]:
    return {
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "system": platform.system(),
        "machine": platform.machine(),
        "byteorder": sys.byteorder,
        "standard_library_only": True,
        "tested_prerequisite": "CPython 3.11 or newer on a POSIX-like system with resource limits; the semantic modules themselves use only the standard library",
        "limits": limits,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--region-instances", type=int, default=384)
    parser.add_argument("--region-seed", type=int, default=20260915)
    parser.add_argument("--skip-fanout", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.region_instances <= 1024:
        raise SystemExit("--region-instances must be in 1..1024")
    output = args.output_dir.resolve()
    require_external_output(output)

    initial_digest, initial_files, initial_bytes = tree_digest(_artifact_files())
    limits = configure_resources()
    process_started = time.process_time()
    wall_started = time.monotonic()

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="bounded-string-campaign-", dir=output.parent) as temporary:
        stage = Path(temporary) / output.name
        stage.mkdir()
        copy_inputs(stage)
        generated_results = stage / "generated" / "results"
        generated_certificates = stage / "generated" / "certificates" / "branch"
        generated_results.mkdir(parents=True)

        cases = regenerated_cases()
        materialization = compare_materialized_cases(cases)
        primitive = primitive_oracle()
        full_abstraction = check_full_abstraction()
        region = check_regions(args.region_instances, args.region_seed)
        rows, proofs, certificates = produce_and_replay(cases, generated_certificates)
        mutation_case, mutation_proof = select_mutation_case(cases, proofs)
        mutation = check_mutations(mutation_case, mutation_proof)
        fanout = (
            {"status": "not_run_by_request", "counted_solver_checker_obligations": 0}
            if args.skip_fanout else run_fanout(cases[-1])
        )
        cli = independent_cli_smoke(generated_certificates)

        obligations = {
            "case_materialization_checks": materialization["checker_obligations"],
            "region_crosscheck": region["counted_solver_checker_obligations"],
            "certificate_campaign": certificates["counted_solver_checker_obligations"],
            "mutation_suite": mutation["counted_solver_mutation_checker_obligations"],
            "fanout_control": fanout.get("counted_solver_checker_obligations", 0),
            "independent_cli_smoke": cli["counted_obligations"],
            "full_abstraction_pair_checks": full_abstraction["pair_checks_total"],
        }
        obligations["campaign_total"] = sum(obligations.values())

        write_csv(generated_results / "branch_cases.csv", rows)
        for name, value in (
            ("primitive_oracle.json", primitive),
            ("full_abstraction_check.json", full_abstraction),
            ("region_crosscheck.json", region),
            ("mutation_suite.json", mutation),
            ("fanout_control.json", fanout),
            ("independent_cli_smoke.json", cli),
        ):
            (generated_results / name).write_text(json_text(value), encoding="utf-8")

        # Closure checks use only generated files and recomputed summaries.
        certificate_paths = sorted(generated_certificates.glob("C*.json"))
        if len(certificate_paths) != 166 or (generated_certificates / "C167.json").exists():
            raise AssertionError("generated certificate closure")
        if sum(json.loads(path.read_text())["leaves"] for path in certificate_paths) != certificates["leaves"]:
            raise AssertionError("generated leaf closure")
        closure = {
            "status": "pass",
            "case_rows": len(rows),
            "certificate_files": len(certificate_paths),
            "certificate_bytes": sum(path.stat().st_size for path in certificate_paths),
            "nodes": certificates["nodes"],
            "leaves": certificates["leaves"],
            "closed_branches": certificates["closed_branches"],
            "all_expected_labels_matched": certificates["expected_labels_matched"] == 166,
            "all_certificates_serialized_reread_same_process": all(
                row["replay_mode"] == "serialized_file_reread_same_process" for row in rows
            ),
            "independent_cli_smoke_cases": 1,
        }

        after_digest, after_files, after_bytes = tree_digest(_artifact_files())
        integrity = {
            "status": "pass" if (initial_digest, initial_files, initial_bytes) == (after_digest, after_files, after_bytes) else "fail",
            "scientific_input_tree_sha256_before": initial_digest,
            "scientific_input_tree_sha256_after": after_digest,
            "scientific_input_file_count_before": initial_files,
            "scientific_input_file_count_after": after_files,
            "scientific_input_bytes_before": initial_bytes,
            "scientific_input_bytes_after": after_bytes,
            "digest_scope": "all artifact files except bytecode/cache and the self-referential results/isolated_campaign_acceptance.json record",
            "excluded_self_record": SELF_ACCEPTANCE_RECORD.as_posix(),
            "artifact_inputs_unchanged": initial_digest == after_digest,
            "output_outside_artifact_root": True,
        }
        if integrity["status"] != "pass":
            raise AssertionError("read-only artifact input integrity changed")

        resources = {
            **limits,
            "process_cpu_seconds": time.process_time() - process_started,
            "wall_seconds": time.monotonic() - wall_started,
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        }
        summary = {
            "status": "pass",
            "campaign_scope": "new isolated campaign; no historical ledger totals are imported",
            "platform": platform_record(limits),
            "case_materialization": materialization,
            "primitive_oracle": primitive,
            "full_abstraction_audit": full_abstraction,
            "region_crosscheck": region,
            "certificate_campaign": certificates,
            "mutation_suite": mutation,
            "fanout_control": fanout,
            "independent_cli_smoke": cli,
            "obligation_accounting": obligations,
            "result_closure": closure,
            "input_integrity": integrity,
            "resources": resources,
            "replay_modes": {
                "all_166_generated_certificates": "serialized file reread, same campaign process",
                "independent_process_smoke": "C135 only",
                "no_claim": "not every certificate is replayed in a fresh process",
            },
        }
        (stage / "campaign_summary.json").write_text(json_text(summary), encoding="utf-8")
        ledger_rows = [
            {"category": key, "count": value, "unit": "counted obligation"}
            for key, value in obligations.items() if key != "campaign_total"
        ]
        ledger_rows.append({"category": "campaign_total", "count": obligations["campaign_total"], "unit": "counted obligation"})
        ledger_rows.extend([
            {"category": "primitive_oracle", "count": primitive["concrete_state_evaluations"], "unit": "concrete input assignments"},
            {"category": "region_crosscheck", "count": region["brute_force_assignments"], "unit": "concrete input assignments"},
            {"category": "fixed_basis", "count": full_abstraction["fixed_basis"]["pair_test_comparisons"], "unit": "pair/test observation comparisons"},
            {"category": "state_dependent_witnesses", "count": full_abstraction["state_dependent_witnesses"]["context_comparisons"], "unit": "pair/context observation comparisons"},
            {"category": "full_abstraction", "count": full_abstraction["all_audit_program_executions"], "unit": "single-side program executions"},
        ])
        write_csv(stage / "campaign_ledger.csv", ledger_rows)
        (stage / "README.md").write_text(
            "# Isolated reproduction campaign\n\n"
            "This directory was created outside the artifact root. The original artifact "
            "was treated as read-only and its scoped scientific-input digest is recorded in "
            "`campaign_summary.json`. New certificates/results are under `generated/`; "
            "a complete snapshot of static artifact assets is under `static-inputs/artifact/`; "
            "retained historical results/certificates are under `retained-evidence/artifact/`. "
            "The self-referential isolated acceptance record is excluded from the digest and "
            "snapshots. All 166 generated "
            "certificates were serialized and re-read before replay in the campaign process. "
            "Only C135 additionally received an independent CLI-process replay.\n",
            encoding="utf-8",
        )
        stage.rename(output)

    signal.alarm(0)
    print(json.dumps({
        "status": "PASS",
        "output_dir": str(output),
        "certified_cases": 166,
        "campaign_obligations": obligations["campaign_total"],
        "artifact_inputs_unchanged": True,
        "fanout_status": fanout["status"],
        "independent_cli_smoke": "C135",
    }, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, OSError, ValueError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error))
