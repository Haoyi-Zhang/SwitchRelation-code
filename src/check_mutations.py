"""Fail-closed mutation checks for retained branch certificates."""
from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path
from typing import Any, Callable

import branch_replay
from replay import Invalid


def first_node(proof: dict[str, Any], kind: str) -> int:
    for index, node in enumerate(proof["nodes"]):
        if isinstance(node, dict) and node.get("kind") == kind:
            return index
    raise AssertionError(f"certificate has no {kind} node")


def rejected(case: dict[str, Any], mutant: dict[str, Any]) -> str:
    try:
        branch_replay.check(case, mutant)
    except (Invalid, KeyError, TypeError, ValueError, RecursionError, OSError) as error:
        return str(error)
    raise AssertionError("mutated certificate was accepted")


def run(case: dict[str, Any], proof: dict[str, Any]) -> dict[str, Any]:
    mutations: list[tuple[str, Callable[[dict[str, Any]], None]]] = []

    def add(name: str, action: Callable[[dict[str, Any]], None]) -> None:
        mutations.append((name, action))

    add("statement_binding", lambda p: p["statement"].__setitem__("id", "mutated"))
    add("wrong_verdict", lambda p: p.__setitem__("verdict", "different" if p["verdict"] == "equivalent" else "equivalent"))
    add("wrong_least_input", lambda p: p.__setitem__("least_input", [255] * len(case["variables"])))
    add("wrong_leaf_total", lambda p: p.__setitem__("leaves", p["leaves"] + 1))
    add("wrong_closed_total", lambda p: p.__setitem__("closed_branches", p["closed_branches"] + 1))
    add("wrong_depth_total", lambda p: p.__setitem__("max_predicates", p["max_predicates"] + 1))
    add("wrong_feasibility", lambda p: p["feasibility"].__setitem__("verdict", "different_inputs" if p["feasibility"]["verdict"] == "same_inputs" else "same_inputs"))
    add("non_integer_float", lambda p: p.__setitem__("leaves", 1.0))
    add("boolean_as_integer", lambda p: p.__setitem__("closed_branches", True))

    leaf = first_node(proof, "leaf")
    split = first_node(proof, "split")

    def bad_leaf_result(p: dict[str, Any]) -> None:
        node = p["nodes"][leaf]
        node["left"] = ["accept", [987654321]]

    def bad_leaf_minimum(p: dict[str, Any]) -> None:
        node = p["nodes"][leaf]
        node["minimum"] = [255] * len(case["variables"])

    def bad_query(p: dict[str, Any]) -> None:
        node = p["nodes"][split]
        node["query"] = ["cmp", 0, 0]

    def missing_child(p: dict[str, Any]) -> None:
        node = p["nodes"][split]
        for index, child in enumerate(node["children"]):
            if type(child) is int:
                node["children"][index] = None
                return
        raise AssertionError("split has no feasible child")

    def repeated_child(p: dict[str, Any]) -> None:
        node = p["nodes"][split]
        feasible = [index for index, child in enumerate(node["children"]) if type(child) is int]
        if not feasible:
            raise AssertionError("split has no feasible child")
        node["children"][feasible[0]] = split

    def unreachable_node(p: dict[str, Any]) -> None:
        p["nodes"].append(copy.deepcopy(p["nodes"][leaf]))

    def delete_node(p: dict[str, Any]) -> None:
        p["nodes"].pop()

    add("leaf_operational_result", bad_leaf_result)
    add("leaf_minimum", bad_leaf_minimum)
    add("split_query", bad_query)
    add("missing_feasible_child", missing_child)
    add("repeated_node", repeated_child)
    add("unreachable_node", unreachable_node)
    add("truncated_node_array", delete_node)

    before = branch_replay.DOMAIN_CALLS
    outcomes = []
    for name, action in mutations:
        mutant = copy.deepcopy(proof)
        action(mutant)
        message = rejected(case, mutant)
        outcomes.append({"mutation": name, "status": "rejected", "message": message})

    parser_outcomes = []
    with tempfile.TemporaryDirectory(prefix="certificate-parser-") as directory:
        duplicate = Path(directory) / "duplicate.json"
        duplicate.write_text('{"a":1,"a":2}\n', encoding="utf-8")
        try:
            branch_replay.load(duplicate)
        except Invalid as error:
            parser_outcomes.append({"mutation": "duplicate_json_key", "status": "rejected", "message": str(error)})
        else:
            raise AssertionError("duplicate key accepted")
        nonfinite = Path(directory) / "nonfinite.json"
        nonfinite.write_text('{"a":NaN}\n', encoding="utf-8")
        try:
            branch_replay.load(nonfinite)
        except Invalid as error:
            parser_outcomes.append({"mutation": "nonfinite_number", "status": "rejected", "message": str(error)})
        else:
            raise AssertionError("non-finite number accepted")

    calls = branch_replay.DOMAIN_CALLS - before
    attempts = len(outcomes) + len(parser_outcomes)
    return {
        "status": "pass",
        "case_id": case["id"],
        "certificate_mutations": outcomes,
        "parser_mutations": parser_outcomes,
        "mutation_attempts": attempts,
        "replayer_domain_calls": calls,
        "counted_solver_mutation_checker_obligations": attempts + calls,
    }
