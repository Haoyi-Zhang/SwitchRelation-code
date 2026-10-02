#!/usr/bin/env python3
"""Validate one isolated campaign directory and write a compact acceptance record."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key in {path}: {key}")
            result[key] = value
        return result

    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=unique,
        parse_constant=lambda token: (_ for _ in ()).throw(
            ValueError(f"non-finite token in {path}: {token}")
        ),
    )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def summarize(campaign: Path) -> dict[str, Any]:
    summary_path = campaign / "campaign_summary.json"
    summary = load_json(summary_path)
    require(summary.get("status") == "pass", "campaign did not pass")
    integrity = summary.get("input_integrity", {})
    closure = summary.get("result_closure", {})
    certificates = summary.get("certificate_campaign", {})
    fanout = summary.get("fanout_control", {})
    cli = summary.get("independent_cli_smoke", {})
    obligations = summary.get("obligation_accounting", {})
    replay_modes = summary.get("replay_modes", {})

    require(integrity.get("status") == "pass", "input integrity failed")
    require(integrity.get("artifact_inputs_unchanged") is True, "artifact input changed")
    require(
        integrity.get("scientific_input_tree_sha256_before")
        == integrity.get("scientific_input_tree_sha256_after"),
        "scientific input digest changed",
    )
    require(closure.get("status") == "pass", "result closure failed")
    require(closure.get("certificate_files") == 166, "certificate count")
    require(closure.get("case_rows") == 166, "case row count")
    require(closure.get("nodes") == 9_986, "node total")
    require(closure.get("leaves") == 6_281, "leaf total")
    require(closure.get("closed_branches") == 1_281, "closed total")
    require(certificates.get("equivalent_cases") == 150, "equivalent total")
    require(certificates.get("different_cases") == 16, "different total")
    require(fanout.get("case_id") == "C167", "fanout case")
    require(fanout.get("status") == "unknown_resource_exhaustion", "fanout status")
    require(fanout.get("schema_expected_field") == "equivalent", "C167 default field")
    require(cli.get("case_id") == "C135", "CLI smoke case")
    require(cli.get("replayer_region_calls") == 4, "CLI regional calls")
    require(cli.get("top_level_checker_obligations") == 1, "CLI top-level checks")
    require(cli.get("counted_obligations") == 5, "CLI counted obligations")
    require(
        replay_modes.get("independent_process_smoke") == "C135 only",
        "process-isolation scope",
    )

    generated_certificates = campaign / "generated" / "certificates" / "branch"
    generated_results = campaign / "generated" / "results"
    require(generated_certificates.is_dir(), "generated certificate directory missing")
    require(generated_results.is_dir(), "generated result directory missing")
    require(len(list(generated_certificates.glob("C*.json"))) == 166, "generated certificate closure")
    require((campaign / "static-inputs" / "artifact").is_dir(), "static asset snapshot missing")
    require((campaign / "retained-evidence" / "artifact" / "results").is_dir(), "retained results snapshot missing")
    require((campaign / "retained-evidence" / "artifact" / "certificates").is_dir(), "retained certificates snapshot missing")

    return {
        "status": "pass",
        "scope": "post-repair isolated acceptance campaign; separate from the frozen historical 99,999 ledger",
        "campaign_summary": "campaign_summary.json in the separately delivered isolated-campaign directory",
        "source": "disposable read-only copy of the artifact; all outputs external to that copy",
        "artifact_inputs_unchanged": True,
        "digest_scope": integrity.get("digest_scope"),
        "excluded_self_record": integrity.get("excluded_self_record"),
        "scientific_input_tree_sha256_before": integrity.get("scientific_input_tree_sha256_before"),
        "scientific_input_tree_sha256_after": integrity.get("scientific_input_tree_sha256_after"),
        "input_file_count": integrity.get("scientific_input_file_count_before"),
        "input_bytes": integrity.get("scientific_input_bytes_before"),
        "platform": summary.get("platform"),
        "certificate_replay_mode": {
            "all_166_generated_certificates": replay_modes.get("all_166_generated_certificates"),
            "independent_process_smoke": replay_modes.get("independent_process_smoke"),
            "no_claim": replay_modes.get("no_claim"),
        },
        "result_closure": closure,
        "campaign_obligation_accounting": obligations,
        "fanout_control": fanout,
        "independent_cli_smoke": cli,
        "static_assets_snapshot": "static-inputs/artifact",
        "retained_evidence_snapshot": "retained-evidence/artifact",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args.campaign.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "output": str(args.output.resolve())}, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        raise SystemExit(str(error))
