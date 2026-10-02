"""Static package inspection; never imports or executes the research implementation."""
from __future__ import annotations

import ast
import csv
import json
from pathlib import Path
from typing import Any


EXPECTED_CASES = [f"C{i:03d}" for i in range(1, 168)]
EXPECTED_CERTIFICATES = EXPECTED_CASES[:-1]
EXPECTED = {
    "certificate_bytes": 1_243_986,
    "nodes": 9_986,
    "leaves": 6_281,
    "closed_branches": 1_281,
    "certified_cases": 166,
    "case_count": 167,
    "equivalent_cases": 150,
    "different_cases": 16,
    "producer_domain_calls": 11_267,
    "replayer_domain_calls": 11_267,
    "mutation_attempts": 18,
    "continuation_obligations": 8_608,
    "continuation_direct_assignments": 480_697,
    "continuation_cumulative_obligations": 99_695,
    "continuation_remaining_obligations": 305,
    "final_clean_certificates_replayed": 5,
    "final_clean_replayer_region_calls": 299,
    "final_clean_top_level_obligations": 5,
    "final_clean_obligations": 304,
    "legacy_mixed_concrete_field": 650_557,
    "cumulative_obligations": 99_999,
    "obligation_ceiling": 100_000,
    "remaining_obligations": 1,
    "reference_audit_rows": 48,
    "reference_doi_rows": 45,
    "reference_official_url_rows": 3,
    "reference_substantive_scope_rows": 20,
    "reference_metadata_scope_rows": 28,
}


def load_json(path: Path) -> Any:
    def reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key in {path}: {key}")
            result[key] = value
        return result

    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=reject_duplicate,
        parse_constant=lambda token: (_ for _ in ()).throw(
            ValueError(f"Non-finite JSON token in {path}: {token}")
        ),
    )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def parse_python(root: Path) -> int:
    paths = sorted(root.rglob("*.py"))
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path.relative_to(root)))
        require(not any(isinstance(node, ast.Assert) for node in ast.walk(tree)),
                f"Scientific integrity check uses assert and would disappear under -O: {path.relative_to(root)}")
    return len(paths)


def inspect_cases(root: Path) -> int:
    paths = sorted((root / "cases").glob("C*.json"))
    require([path.stem for path in paths] == EXPECTED_CASES, "Case set is not exactly C001-C167")
    for path in paths:
        case = load_json(path)
        require(isinstance(case, dict), f"Case is not an object: {path.name}")
        require(case.get("id") == path.stem, f"Case identifier/file mismatch: {path.name}")
    return len(paths)


def inspect_certificate(path: Path) -> dict[str, int | str]:
    cert = load_json(path)
    require(isinstance(cert, dict), f"Certificate is not an object: {path.name}")
    statement = cert.get("statement")
    require(isinstance(statement, dict), f"Missing statement: {path.name}")
    require(statement.get("id") == path.stem, f"Certificate statement mismatch: {path.name}")
    nodes = cert.get("nodes")
    require(isinstance(nodes, list) and nodes, f"Missing node array: {path.name}")

    reachable: set[int] = set()
    active: set[int] = set()
    leaf_count = 0
    closed_count = 0

    def visit(index: int) -> None:
        nonlocal leaf_count, closed_count
        require(type(index) is int and 0 <= index < len(nodes), f"Bad node reference in {path.name}")
        require(index not in active, f"Cycle in {path.name}")
        require(index not in reachable, f"Repeated node reference in {path.name}")
        active.add(index)
        reachable.add(index)
        node = nodes[index]
        require(isinstance(node, dict), f"Non-object node in {path.name}")
        kind = node.get("kind")
        if kind == "leaf":
            leaf_count += 1
        elif kind == "split":
            children = node.get("children")
            choices = node.get("choices")
            require(isinstance(children, list) and isinstance(choices, list), f"Bad split in {path.name}")
            require(len(children) == len(choices) and len(children) >= 2, f"Bad split arity in {path.name}")
            for child in children:
                if child is None:
                    closed_count += 1
                else:
                    visit(child)
        else:
            raise ValueError(f"Unknown node kind in {path.name}: {kind!r}")
        active.remove(index)

    visit(0)
    require(len(reachable) == len(nodes), f"Unreachable node in {path.name}")
    require(cert.get("leaves") == leaf_count, f"Leaf total mismatch in {path.name}")
    require(cert.get("closed_branches") == closed_count, f"Closed total mismatch in {path.name}")
    verdict = cert.get("verdict")
    require(verdict in {"equivalent", "different"}, f"Bad verdict in {path.name}")
    return {
        "id": path.stem,
        "nodes": len(nodes),
        "leaves": leaf_count,
        "closed_branches": closed_count,
        "bytes": path.stat().st_size,
        "verdict": verdict,
    }


def inspect_certificates(root: Path) -> dict[str, Any]:
    cert_dir = root / "certificates" / "branch"
    paths = sorted(cert_dir.glob("C*.json"))
    require([path.stem for path in paths] == EXPECTED_CERTIFICATES,
            "Certificate set is not exactly C001-C166")
    require(not (cert_dir / "C167.json").exists(), "C167 must not have a completed certificate")
    rows = [inspect_certificate(path) for path in paths]
    totals = {
        "certificate_files": len(rows),
        "certificate_bytes": sum(int(row["bytes"]) for row in rows),
        "nodes": sum(int(row["nodes"]) for row in rows),
        "leaves": sum(int(row["leaves"]) for row in rows),
        "closed_branches": sum(int(row["closed_branches"]) for row in rows),
        "equivalent_cases": sum(row["verdict"] == "equivalent" for row in rows),
        "different_cases": sum(row["verdict"] == "different" for row in rows),
        "rows": rows,
    }
    for key in ("certificate_bytes", "nodes", "leaves", "closed_branches",
                "equivalent_cases", "different_cases"):
        require(totals[key] == EXPECTED[key], f"Certificate-derived {key} mismatch")
    require(totals["certificate_files"] == EXPECTED["certified_cases"],
            "Certificate-count mismatch")
    return totals


def inspect_branch_csv(root: Path, certs: dict[str, Any]) -> None:
    path = root / "results" / "branch_cases.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    require([row.get("id") for row in rows] == EXPECTED_CERTIFICATES,
            "branch_cases.csv is not exactly C001-C166")
    by_id = {str(row["id"]): row for row in certs["rows"]}
    for row in rows:
        cert = by_id[str(row["id"])]
        for csv_key, cert_key in (
            ("nodes", "nodes"), ("leaves", "leaves"),
            ("closed_branches", "closed_branches"), ("certificate_bytes", "bytes")
        ):
            require(int(row[csv_key]) == int(cert[cert_key]),
                    f"CSV/certificate mismatch for {row['id']} {csv_key}")
        require(row["verdict"] == cert["verdict"],
                f"CSV/certificate verdict mismatch for {row['id']}")


def inspect_results(root: Path, certs: dict[str, Any]) -> dict[str, Any]:
    result_dir = root / "results"
    for path in sorted(result_dir.glob("*.json")):
        load_json(path)
    final = load_json(result_dir / "final_reproduction.json")
    require(final.get("status") == "pass", "Final reproduction status is not pass")

    branch = final["branch_certificates"]
    comparisons = {
        "certificate_bytes": certs["certificate_bytes"],
        "certified_cases": certs["certificate_files"],
        "closed_branches": certs["closed_branches"],
        "different_cases": certs["different_cases"],
        "equivalent_cases": certs["equivalent_cases"],
        "leaves": certs["leaves"],
        "nodes": certs["nodes"],
    }
    for key, value in comparisons.items():
        require(branch.get(key) == value, f"Final branch summary mismatch: {key}")
    require(branch.get("producer_domain_calls") == EXPECTED["producer_domain_calls"],
            "Producer-domain-call mismatch")
    require(branch.get("replayer_domain_calls") == EXPECTED["replayer_domain_calls"],
            "Replayer-domain-call mismatch")
    require(final["case_materialization"].get("case_count") == EXPECTED["case_count"],
            "Final case-count mismatch")

    fanout = load_json(result_dir / "fanout_control.json")
    require(fanout.get("case_id") == "C167", "Fanout control is not C167")
    require(fanout.get("status") == "unknown_resource_exhaustion",
            "C167 must remain unknown_resource_exhaustion")
    require(fanout.get("node_limit") == 6000 and fanout.get("producer_domain_calls") == 6055,
            "C167 cap evidence mismatch")
    require(final.get("fanout_control") == fanout, "Embedded C167 summary mismatch")

    mutation = load_json(result_dir / "mutation_suite.json")
    require(mutation.get("status") == "pass", "Mutation suite status is not pass")
    require(mutation.get("mutation_attempts") == EXPECTED["mutation_attempts"],
            "Mutation-attempt count mismatch")
    mutation_rows = mutation.get("certificate_mutations", []) + mutation.get("parser_mutations", [])
    require(len(mutation_rows) == EXPECTED["mutation_attempts"], "Mutation row count mismatch")
    require(all(row.get("status") == "rejected" for row in mutation_rows),
            "A mutation was not rejected")

    with (result_dir / "resource_accounting.csv").open(newline="", encoding="utf-8") as handle:
        accounting = list(csv.DictReader(handle))
    require(accounting, "Empty resource accounting")
    counted = sum(int(row["counted_obligations"]) for row in accounting)
    concrete = sum(int(row["concrete_state_evaluations"]) for row in accounting)
    resource = final["resource_accounting"]
    require(counted == resource.get("cumulative_obligations") == EXPECTED["cumulative_obligations"],
            "Cumulative obligation mismatch")
    require(resource.get("obligation_ceiling") == EXPECTED["obligation_ceiling"],
            "Obligation ceiling mismatch")
    require(resource.get("remaining_obligations") == EXPECTED["remaining_obligations"],
            "Remaining-obligation mismatch")
    legacy_mixed = concrete
    require(legacy_mixed == resource.get("cumulative_direct_concrete_assignment_checks")
            == EXPECTED["legacy_mixed_concrete_field"],
            "Legacy mixed concrete-field accounting mismatch")
    require(resource.get("continuation_obligations") == EXPECTED["continuation_obligations"],
            "Continuation-obligation mismatch")
    require(resource.get("continuation_direct_concrete_assignment_checks")
            == EXPECTED["continuation_direct_assignments"],
            "Continuation direct-assignment mismatch")

    audit = load_json(result_dir / "final_continuation_audit.json")
    require(final.get("continuation_audit") == audit,
            "Embedded continuation audit mismatch")
    require(audit.get("status") == "pass", "Continuation audit status is not pass")
    audit_resource = audit.get("resource_accounting", {})
    require(audit_resource.get("new_counted_obligations")
            == EXPECTED["continuation_obligations"],
            "Continuation counted-obligation mismatch")
    require(audit_resource.get("new_direct_concrete_assignment_checks")
            == EXPECTED["continuation_direct_assignments"],
            "Continuation direct-assignment mismatch")
    require(audit_resource.get("cumulative_counted_obligations")
            == EXPECTED["continuation_cumulative_obligations"],
            "Continuation cumulative-obligation mismatch")
    require(audit_resource.get("remaining_obligations")
            == EXPECTED["continuation_remaining_obligations"],
            "Continuation remaining-obligation mismatch")
    require(audit.get("case_materialization", {}).get("case_count") == EXPECTED["case_count"],
            "Continuation case-materialization mismatch")
    replay = audit.get("fresh_certificate_replay", {})
    require(replay.get("certificates_replayed") == 165,
            "Continuation fresh-replay count mismatch")
    require(replay.get("excluded_from_fresh_replay") == "C166",
            "Continuation C166 exclusion mismatch")
    direct = audit.get("direct_concrete_audit", {})
    require(direct.get("assignment_checks") == EXPECTED["continuation_direct_assignments"],
            "Continuation direct-audit mismatch")
    require(direct.get("leaf_minima_recomputed") == EXPECTED["leaves"],
            "Continuation leaf-minimum audit mismatch")
    fresh_mutation = audit.get("fresh_mutation_suite", {})
    require(fresh_mutation.get("mutation_attempts") == EXPECTED["mutation_attempts"]
            and all(row.get("status") == "rejected" for row in
                    fresh_mutation.get("certificate_mutations", [])
                    + fresh_mutation.get("parser_mutations", [])),
            "Continuation mutation audit mismatch")
    require(audit.get("fresh_region_solver_crosscheck", {}).get("region_instances") == 320,
            "Continuation region cross-check mismatch")

    clean = load_json(result_dir / "final_clean_extract_audit.json")
    require(final.get("final_clean_extract_audit") == clean,
            "Embedded final clean-extract audit mismatch")
    require(clean.get("status") == "pass", "Final clean-extract audit status is not pass")
    require(clean.get("selection") == ["C061", "C062", "C065", "C162", "C163"],
            "Final clean-extract selection mismatch")
    require(clean.get("certificates_replayed") == EXPECTED["final_clean_certificates_replayed"],
            "Final clean-extract replay count mismatch")
    require(clean.get("replayer_region_calls") == EXPECTED["final_clean_replayer_region_calls"],
            "Final clean-extract region-call mismatch")
    require(clean.get("top_level_checker_obligations")
            == EXPECTED["final_clean_top_level_obligations"],
            "Final clean-extract top-level-check mismatch")
    require(clean.get("new_counted_obligations") == EXPECTED["final_clean_obligations"],
            "Final clean-extract obligation mismatch")
    require(clean.get("inherited_counted_obligations")
            == EXPECTED["continuation_cumulative_obligations"],
            "Final clean-extract inherited-total mismatch")
    require(clean.get("cumulative_counted_obligations") == EXPECTED["cumulative_obligations"],
            "Final clean-extract cumulative-total mismatch")
    require(clean.get("remaining_obligations") == EXPECTED["remaining_obligations"],
            "Final clean-extract remaining-total mismatch")

    full_reconciliation = load_json(result_dir / "full_abstraction_reconciliation.json")
    require(full_reconciliation.get("status") == "pass", "Full-abstraction reconciliation failed")
    require(full_reconciliation.get("base_ordered_pair_checks") == 1296
            and full_reconciliation.get("directed_control_checks") == 3
            and full_reconciliation.get("pair_checks_total") == 1299,
            "Full-abstraction pair decomposition mismatch")
    require(full_reconciliation.get("fixed_basis", {}).get("instantiated_tests_per_pair") == 18
            and full_reconciliation.get("fixed_basis", {}).get("syntactic_templates") == 3,
            "Fixed complete basis mismatch")
    require(full_reconciliation.get("byte_2_vs_3_sanity", {}).get("fixed_low_bit_probe_distinguishes") is True,
            "Byte 2/3 fixed-probe sanity missing")
    signature = full_reconciliation.get("all_byte_signature_audit", {})
    require(signature.get("unique_signatures") == 256
            and signature.get("ordered_byte_pair_checks") == 65_536
            and signature.get("unequal_byte_pair_checks") == 65_280
            and signature.get("unequal_byte_pairs_distinguished") == 65_280,
            "All-byte fixed-probe signature audit mismatch")
    require(full_reconciliation.get("fixed_basis", {}).get("pair_test_comparisons") == 23_382
            and full_reconciliation.get("fixed_basis", {}).get("single_side_program_executions") == 46_764
            and full_reconciliation.get("state_dependent_witnesses", {}).get("context_comparisons") == 1_262
            and full_reconciliation.get("all_audit_program_executions") == 49_294,
            "Full-abstraction unit accounting mismatch")

    mutation_grouping = load_json(result_dir / "mutation_grouping.json")
    require(mutation_grouping.get("status") == "pass"
            and mutation_grouping.get("group_sizes") == [7, 4, 3, 4]
            and mutation_grouping.get("total_mutations") == 18,
            "Mutation grouping mismatch")

    accounting = load_json(result_dir / "accounting_scope_reconciliation.json")
    require(accounting.get("status") == "pass", "Accounting reconciliation failed")
    require(accounting.get("frozen_obligation_ledger", {}).get("counted_obligations") == 99999
            and accounting.get("frozen_obligation_ledger", {}).get("all_time_total") == "unknown"
            and accounting.get("frozen_obligation_ledger", {}).get("same_rule_lower_bound_after_C135_cli") == 100004,
            "Frozen-ledger scope mismatch")
    require(accounting.get("region_enumeration_disclosure", {}).get("continuation_brute_force_assignments") == 9872,
            "Continuation region enumeration missing")

    smoke_accounting = load_json(result_dir / "documented_replay_smoke_accounting.json")
    require(smoke_accounting.get("replayer_region_calls") == 4
            and smoke_accounting.get("top_level_checker_obligations") == 1
            and smoke_accounting.get("counted_obligations_under_frozen_rule") == 5
            and smoke_accounting.get("included_in_frozen_99999_ledger") is False,
            "Documented CLI smoke accounting mismatch")

    process_modes = load_json(result_dir / "process_isolation_reconciliation.json")
    require(process_modes.get("status") == "pass"
            and process_modes.get("original_batch", {}).get("fresh_process_per_certificate") is False
            and process_modes.get("isolated_campaign", {}).get("independent_cli_smoke") == "C135 only"
            and process_modes.get("documented_C135_cli_smoke", {}).get("counted_obligations") == 5,
            "Process-isolation reconciliation mismatch")

    c167 = load_json(result_dir / "C167_status_reconciliation.json")
    require(c167.get("schema_expected_field") == "equivalent"
            and c167.get("cap_status") == "unknown_resource_exhaustion"
            and c167.get("included_in_166_completed_verdicts") is False,
            "C167 status reconciliation mismatch")

    isolated = load_json(result_dir / "isolated_campaign_acceptance.json")
    require(isolated.get("status") == "pass"
            and isolated.get("artifact_inputs_unchanged") is True
            and isolated.get("result_closure", {}).get("certificate_files") == 166
            and isolated.get("independent_cli_smoke", {}).get("counted_obligations") == 5,
            "Isolated campaign acceptance mismatch")

    return {
        "campaign_status": final["status"],
        "fanout_status": fanout["status"],
        "cumulative_obligations": counted,
        "remaining_obligations": resource["remaining_obligations"],
        "legacy_mixed_concrete_field": legacy_mixed,
        "final_clean_replay_status": clean["status"],
        "final_clean_certificates_replayed": clean["certificates_replayed"],
        "final_clean_replayer_region_calls": clean["replayer_region_calls"],
        "final_clean_obligations": clean["new_counted_obligations"],
        "fixed_basis_tests_per_pair": full_reconciliation["fixed_basis"]["instantiated_tests_per_pair"],
        "isolated_campaign_status": isolated["status"],
        "all_time_obligation_total": "unknown",
    }



def inspect_spec_code_map(root: Path) -> int:
    path = root / "SPEC-CODE-MAP.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    require(rows, "Empty specification--code map")
    cache: dict[Path, dict[str, int]] = {}
    for row in rows:
        source = root / row["Implementation file"]
        require(source.is_file(), f"Missing mapped source: {row['Implementation file']}")
        if source not in cache:
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source.relative_to(root)))
            symbols: dict[str, int] = {}
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    symbols[node.name] = node.lineno
                    if isinstance(node, ast.ClassDef):
                        for child in node.body:
                            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                symbols[f"{node.name}.{child.name}"] = child.lineno
            cache[source] = symbols
        symbol = row["Symbol"]
        require(symbol in cache[source], f"Unresolved mapped symbol: {row['Implementation file']}::{symbol}")
        try:
            recorded = int(row["Definition line"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid mapped line for {symbol}") from exc
        require(recorded == cache[source][symbol],
                f"Stale mapped line for {row['Implementation file']}::{symbol}: {recorded} != {cache[source][symbol]}")
        require(bool(row.get("Executable evidence")) and bool(row.get("Boundary")),
                f"Incomplete map row for {symbol}")
    return len(rows)

def inspect_ledgers(root: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for name in ("claim_evidence_ledger.csv", "external_resources.csv", "REVIEWER-CLAIM-LEDGER.csv"):
        with (root / name).open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        require(rows, f"Empty ledger: {name}")
        require(all(all(value is not None for value in row.values()) for row in rows),
                f"Malformed row in {name}")
        counts[name] = len(rows)

    reference_path = root / "results" / "reference_audit.csv"
    with reference_path.open(newline="", encoding="utf-8") as handle:
        references = list(csv.DictReader(handle))
    require(len(references) == EXPECTED["reference_audit_rows"],
            "Reference-audit row count mismatch")
    keys = [row.get("citation_key", "") for row in references]
    require(len(set(keys)) == len(keys) and all(keys),
            "Reference-audit keys are missing or duplicated")
    require(all(row.get("cited_in_main_tex") == "yes" for row in references),
            "Reference audit contains an uncited entry")
    require(all(row.get("persistent_identifier_or_official_url", "").startswith("https://")
                for row in references),
            "Reference audit contains a nonpersistent or missing URL")
    require(all(row.get("verification_scope") and row.get("role_in_paper")
                for row in references),
            "Reference audit is missing verification scope or paper role")
    doi_rows = sum("doi.org/" in row["persistent_identifier_or_official_url"]
                   for row in references)
    official_rows = len(references) - doi_rows
    substantive_rows = sum("substantive full-text sections read"
                           in row["verification_scope"].lower() for row in references)
    require(doi_rows == EXPECTED["reference_doi_rows"], "Reference DOI count mismatch")
    require(official_rows == EXPECTED["reference_official_url_rows"],
            "Reference official-URL count mismatch")
    require(substantive_rows == EXPECTED["reference_substantive_scope_rows"],
            "Reference substantive-scope count mismatch")
    require(len(references) - substantive_rows == EXPECTED["reference_metadata_scope_rows"],
            "Reference metadata-scope count mismatch")

    audit = load_json(root / "results" / "reference_integrity_audit.json")
    require(audit.get("status") == "pass", "Reference integrity audit status is not pass")
    require(audit.get("entries") == len(references)
            and audit.get("unique_citation_keys") == len(set(keys))
            and audit.get("cited_in_manuscript") == len(references),
            "Reference integrity audit structural mismatch")
    require(audit.get("doi_entries") == doi_rows
            and audit.get("official_url_entries") == official_rows,
            "Reference integrity audit identifier mismatch")
    require(audit.get("substantive_full_text_section_scopes") == substantive_rows
            and audit.get("bibliographic_metadata_or_proceedings_scopes")
            == len(references) - substantive_rows,
            "Reference integrity audit scope mismatch")
    counts["reference_audit.csv"] = len(references)
    counts["SPEC-CODE-MAP.csv"] = inspect_spec_code_map(root)
    return counts


def inspect(root: Path) -> dict[str, Any]:
    python_files = parse_python(root)
    case_count = inspect_cases(root)
    certs = inspect_certificates(root)
    inspect_branch_csv(root, certs)
    results = inspect_results(root, certs)
    ledger_counts = inspect_ledgers(root)
    return {
        "status": "PACKET_STRUCTURE_OK",
        "semantic_reproduction": "RETAINED_RESULTS_PLUS_FINAL_STRATIFIED_REPLAY",
        "python_files_parsed": python_files,
        "case_schemas": case_count,
        "certificate_files": certs["certificate_files"],
        "certificate_bytes": certs["certificate_bytes"],
        "nodes": certs["nodes"],
        "leaves": certs["leaves"],
        "closed_branches": certs["closed_branches"],
        "equivalent_cases": certs["equivalent_cases"],
        "different_cases": certs["different_cases"],
        "cumulative_obligations": results["cumulative_obligations"],
        "remaining_obligations": results["remaining_obligations"],
        "legacy_mixed_concrete_field": results["legacy_mixed_concrete_field"],
        "campaign_status": results["campaign_status"],
        "fanout_status": results["fanout_status"],
        "final_clean_replay_status": results["final_clean_replay_status"],
        "final_clean_certificates_replayed": results["final_clean_certificates_replayed"],
        "final_clean_replayer_region_calls": results["final_clean_replayer_region_calls"],
        "final_clean_obligations": results["final_clean_obligations"],
        "fixed_basis_tests_per_pair": results["fixed_basis_tests_per_pair"],
        "isolated_campaign_status": results["isolated_campaign_status"],
        "all_time_obligation_total": results["all_time_obligation_total"],
        "claim_ledger_rows": ledger_counts["claim_evidence_ledger.csv"],
        "reviewer_claim_rows": ledger_counts["REVIEWER-CLAIM-LEDGER.csv"],
        "spec_code_map_rows": ledger_counts["SPEC-CODE-MAP.csv"],
        "external_resource_rows": ledger_counts["external_resources.csv"],
        "reference_audit_rows": ledger_counts["reference_audit.csv"],
    }


if __name__ == "__main__":
    try:
        print(json.dumps(inspect(Path(__file__).resolve().parent), indent=2, sort_keys=True))
    except (OSError, ValueError, SyntaxError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise SystemExit("PACKET_INSPECTION_FAILED: " + str(error))
