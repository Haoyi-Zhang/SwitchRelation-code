"""Fresh finite checks with external, incremental evidence and no tree replacement.

Uses only owned cases and the standard library.  It is not a benchmark of any
external application, a proof-assistant check, or the historical campaign driver.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import threading
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]

import branch_replay
import order_domain
from branch_producer import certify
from check_full_abstraction import run as abstraction
from check_mutations import run as mutations
from check_regions import run as regions
from make_cases import build as small_cases
from make_large_cases import build as large_cases, fanout_case
from producer import Rejected


def digest() -> str:
    result = hashlib.sha256()
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        relative = path.relative_to(ROOT).as_posix().encode("utf-8")
        data = path.read_bytes()
        result.update(len(relative).to_bytes(8, "big"))
        result.update(relative)
        result.update(len(data).to_bytes(8, "big"))
        result.update(data)
    return result.hexdigest()


def run(output: Path) -> dict:
    output = output.resolve()
    if output == ROOT or ROOT in output.parents or output in ROOT.parents:
        raise ValueError("evidence must be outside and not an ancestor of the artifact")
    output.mkdir(parents=True, exist_ok=False)
    started, cpu = time.monotonic(), time.process_time()
    before = digest()
    limits = {"wall_seconds": 120, "workers": 1, "memory_limit_bytes": None}
    if os.name == "posix":
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
        resource.setrlimit(resource.RLIMIT_CPU, (100, 110))
        limits.update(memory_limit_bytes=1024**3, cpu_soft_seconds=100, cpu_hard_seconds=110)

    def expired():
        print("INCOMPLETE: 120-second wall limit", flush=True)
        os._exit(124)

    timer = threading.Timer(120, expired)
    timer.daemon = True
    timer.start()

    def record(name, value):
        (output / (name + ".json")).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"phase": name, "wall_seconds": time.monotonic()-started, "result": value}), flush=True)

    record("environment", {"python": sys.version, "platform": platform.platform(),
                           "limits": limits, "input_tree_sha256": before,
                           "scope": "fresh finite checks, separate from historical host measurements"})
    try:
        generated = small_cases() + large_cases() + [fanout_case()]
        if [c["id"] for c in generated] != [f"C{i:03d}" for i in range(1, 168)]:
            raise ValueError("generator identity closure")
        for case in generated:
            if case != branch_replay.load(ROOT / "cases" / (case["id"] + ".json")):
                raise ValueError("case materialization: " + case["id"])
        record("materialization", {"cases": len(generated), "status": "pass"})
        record("abstraction", abstraction())
        record("regions", regions(384, 20261006))
        if os.name == "posix":
            from primitive_oracle import run as primitives
            record("primitives", primitives())
        else:
            record("primitives", {"status": "not_run", "reason": "existing primitive driver requires POSIX resource interfaces"})

        proofs = output / "certificates"
        proofs.mkdir()
        rows = []
        p0, r0 = order_domain.SOLVE_CALLS, branch_replay.DOMAIN_CALLS
        for case in generated[:-1]:
            proof = certify(case)
            path = proofs / (case["id"] + ".json")
            path.write_text(json.dumps(proof, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
            checked = branch_replay.check(case, branch_replay.load(path))
            if checked["verdict"] != case["expected"]:
                raise ValueError("expected label: " + case["id"])
            rows.append(checked)
            with (output / "case_replays.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(checked, sort_keys=True) + "\n")
        totals = {"certificates": len(rows), "nodes": sum(x["nodes"] for x in rows),
                  "leaves": sum(x["leaves"] for x in rows),
                  "closed_branches": sum(x["closed_branches"] for x in rows),
                  "different": sum(x["verdict"] == "different" for x in rows),
                  "producer_region_calls": order_domain.SOLVE_CALLS-p0,
                  "replayer_region_calls": branch_replay.DOMAIN_CALLS-r0,
                  "mode": "fresh serialized-file reread, same process", "status": "pass"}
        if (totals["certificates"], totals["nodes"], totals["leaves"], totals["closed_branches"], totals["different"]) != (166, 9986, 6281, 1281, 16):
            raise ValueError("certificate totals differ from retained corpus")
        record("certificates", totals)
        record("mutations", mutations(generated[0], branch_replay.load(proofs / "C001.json"), evidence_dir=output / "mutations"))
        p0 = order_domain.SOLVE_CALLS
        try:
            certify(generated[-1])
        except Rejected as error:
            if str(error) != "branch node budget":
                raise
            record("fanout", {"case": "C167", "status": "unknown_resource_exhaustion",
                              "reason": str(error), "producer_region_calls": order_domain.SOLVE_CALLS-p0})
        else:
            raise ValueError("C167 unexpectedly completed; requires scientific review")
        after = digest()
        if before != after:
            raise ValueError("artifact input digest changed")
        summary = {"status": "pass", "input_tree_sha256_before": before,
                   "input_tree_sha256_after": after, "wall_seconds": time.monotonic()-started,
                   "process_cpu_seconds": time.process_time()-cpu, "certificate_campaign": totals,
                   "primitive_oracle_run": os.name == "posix",
                   "not_claimed": "historical reproduction, independent process replay, proof mechanization, external application results"}
        record("summary", summary)
        return summary
    except Exception as error:
        record("failure", {"status": "fail", "error_type": type(error).__name__, "error": str(error)})
        raise
    finally:
        timer.cancel()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    run(args.output_dir)
