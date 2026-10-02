#!/usr/bin/env python3
"""Merge explicit isolated campaign summaries without mutating the artifact."""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaigns", nargs="+", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if output.exists():
        raise SystemExit("output directory already exists")
    summaries = []
    for campaign in args.campaigns:
        path = campaign / "campaign_summary.json" if campaign.is_dir() else campaign
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("status") != "pass":
            raise SystemExit(f"campaign is not passing: {path}")
        summaries.append((str(path.resolve()), data))
    output.mkdir(parents=True)
    units = {
        "counted_obligations": sum(item["obligation_accounting"]["campaign_total"] for _, item in summaries),
        "primitive_concrete_assignments": sum(item["primitive_oracle"]["concrete_state_evaluations"] for _, item in summaries),
        "region_concrete_assignments": sum(item["region_crosscheck"]["brute_force_assignments"] for _, item in summaries),
        "fixed_basis_pair_test_comparisons": sum(item["full_abstraction_audit"]["fixed_basis"]["pair_test_comparisons"] for _, item in summaries),
        "witness_context_comparisons": sum(item["full_abstraction_audit"]["state_dependent_witnesses"]["context_comparisons"] for _, item in summaries),
        "single_side_program_executions": sum(item["full_abstraction_audit"]["all_audit_program_executions"] for _, item in summaries),
    }
    merged = {
        "status": "pass",
        "campaign_count": len(summaries),
        "campaigns": [path for path, _ in summaries],
        "separate_units": units,
        "warning": "Only like-for-like units are summed. Historical frozen-ledger values are not imported or deduplicated.",
    }
    (output / "merged_summary.json").write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with (output / "merged_ledger.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["category", "count"])
        writer.writeheader()
        writer.writerows({"category": key, "count": value} for key, value in units.items())
    print(json.dumps(merged, sort_keys=True))


if __name__ == "__main__":
    main()
