"""Finite executable audit of the contextual-equivalence constructions.

The general results remain paper proofs.  This audit separates three quantities:
(1) 1,296 ordered pairs from 36 fixed-capacity base states;
(2) three directed controls for capacity, initialization, and quotiented physical
    representation; and
(3) program executions used by the fixed basis and state-dependent witnesses.
"""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

from contextual import (
    ObjectState,
    State,
    allocation_equivalent,
    distinguishing_continuation,
    fixed_complete_basis,
    run_basis_continuation,
)

CAPACITY_BOUND = 2
OBJECT_NAMES = ("b",)
SCALAR_NAMES = ("r",)


def states() -> list[State]:
    result: list[State] = []
    # Logical two-byte states over {0,1}; payloads below false init bits are fixed
    # only to keep this finite generator canonical.
    for flags in itertools.product((False, True), repeat=2):
        initialized_positions = [index for index, flag in enumerate(flags) if flag]
        for values in itertools.product((0, 1), repeat=len(initialized_positions)):
            payload = [0, 0]
            for index, value in zip(initialized_positions, values):
                payload[index] = value
            obj = ObjectState(tuple(payload), tuple(flags))
            for scalar in (0, 1):
                for emitted in ((), (0,)):
                    result.append(State({"b": obj}, {"r": scalar}, emitted, {}, "bytes"))
    return result


def directed_controls() -> list[tuple[str, State, State, bool]]:
    base = State({"b": ObjectState((0,), (True,))}, {"r": 0})
    return [
        (
            "capacity_mismatch",
            base,
            State({"b": ObjectState((0, 0), (True, True))}, {"r": 0}),
            False,
        ),
        (
            "initialization_mismatch",
            base,
            State({"b": ObjectState((0,), (False,))}, {"r": 0}),
            False,
        ),
        (
            "quotiented_view_cache_uninitialized_payload",
            State({"b": ObjectState((0, 9), (True, False))}, {"r": 0}, (), {("b", 0): 0}, "bytes"),
            State({"b": ObjectState((0, 200), (True, False))}, {"r": 0}, (), {}, "string"),
            True,
        ),
    ]


def observations_equal(left: State, right: State, continuation: list[dict]) -> bool:
    return run_basis_continuation(left, continuation) == run_basis_continuation(right, continuation)


def run() -> dict:
    universe = states()
    basis = fixed_complete_basis(OBJECT_NAMES, SCALAR_NAMES, CAPACITY_BOUND)
    expected_basis_count = 1 + len(SCALAR_NAMES) + 8 * CAPACITY_BOUND * len(OBJECT_NAMES)
    if len(basis) != expected_basis_count:
        raise AssertionError("fixed basis instance count")

    pair_records: list[tuple[str, State, State, bool]] = [
        ("base", left, right, allocation_equivalent(left, right))
        for left in universe
        for right in universe
    ]
    controls = directed_controls()
    pair_records.extend(controls)

    equivalent_pairs = 0
    differing_pairs = 0
    empty_witnesses = 0
    one_command_witnesses = 0
    two_command_witnesses = 0
    fixed_basis_pair_test_comparisons = 0
    unrelated_witness_context_checks = 0

    for source, left, right, expected_related in pair_records:
        related = allocation_equivalent(left, right)
        if related != expected_related:
            raise AssertionError(f"directed-control classification: {source}")

        equal_on_all_basis_tests = True
        for continuation in basis:
            fixed_basis_pair_test_comparisons += 1
            if not observations_equal(left, right, continuation):
                equal_on_all_basis_tests = False
        if equal_on_all_basis_tests != related:
            raise AssertionError(f"fixed basis completeness failure: {source}")

        witness = distinguishing_continuation(left, right)
        if related:
            equivalent_pairs += 1
            if witness is not None:
                raise AssertionError("related pair received a state-dependent witness")
        else:
            differing_pairs += 1
            if witness is None:
                raise AssertionError("unrelated pair has no witness")
            unrelated_witness_context_checks += 1
            if len(witness) == 0:
                empty_witnesses += 1
            elif len(witness) == 1:
                one_command_witnesses += 1
            elif len(witness) == 2:
                two_command_witnesses += 1
            else:
                raise AssertionError("witness length bound")
            if observations_equal(left, right, witness):
                raise AssertionError("state-dependent witness does not distinguish")

    # A fixed equality basis using only literals 0 and 1 does not distinguish 2
    # from 3, whereas the predeclared low-bit mask probe does.
    two = State({"b": ObjectState((2,), (True,))}, {"r": 0})
    three = State({"b": ObjectState((3,), (True,))}, {"r": 0})
    equality_zero = [
        {"op": "byte_eq", "left": {"read": ["b", 0]}, "right": 0, "out": "eq0"},
        {"op": "emit", "value": "$eq0"},
    ]
    equality_one = [
        {"op": "byte_eq", "left": {"read": ["b", 0]}, "right": 1, "out": "eq1"},
        {"op": "emit", "value": "$eq1"},
    ]
    low_bit = [
        {"op": "mask_eq", "value": {"read": ["b", 0]}, "mask": 1, "equal": 1, "out": "bit0"},
        {"op": "emit", "value": "$bit0"},
    ]
    if not observations_equal(two, three, equality_zero):
        raise AssertionError("2/3 equality-to-zero sanity")
    if not observations_equal(two, three, equality_one):
        raise AssertionError("2/3 equality-to-one sanity")
    if observations_equal(two, three, low_bit):
        raise AssertionError("2/3 fixed low-bit probe sanity")

    # The fixed byte-observation template uses all eight single-bit masks.
    # Check the template itself over the complete byte domain, independently of
    # the smaller 0/1 state universe used above.  This is a signature check,
    # not an additional interpreter execution count.
    byte_signatures = {
        value: tuple(bool(value & (1 << bit)) for bit in range(8))
        for value in range(256)
    }
    if len(set(byte_signatures.values())) != 256:
        raise AssertionError("eight-bit probe signature is not injective")
    ordered_byte_pair_checks = 0
    unequal_byte_pair_checks = 0
    unequal_byte_pairs_distinguished = 0
    for left_value in range(256):
        for right_value in range(256):
            ordered_byte_pair_checks += 1
            if left_value != right_value:
                unequal_byte_pair_checks += 1
                if byte_signatures[left_value] != byte_signatures[right_value]:
                    unequal_byte_pairs_distinguished += 1
    if ordered_byte_pair_checks != 65_536:
        raise AssertionError("ordered byte-pair audit cardinality")
    if unequal_byte_pair_checks != 65_280:
        raise AssertionError("unequal byte-pair audit cardinality")
    if unequal_byte_pairs_distinguished != unequal_byte_pair_checks:
        raise AssertionError("fixed byte signature failed to distinguish an unequal pair")

    pair_checks = len(pair_records)
    fixed_basis_single_side_program_executions = 2 * fixed_basis_pair_test_comparisons
    witness_single_side_program_executions = 2 * unrelated_witness_context_checks
    return {
        "status": "pass",
        "base_state_count": len(universe),
        "base_ordered_pair_checks": len(universe) ** 2,
        "directed_control_checks": len(controls),
        "pair_checks_total": pair_checks,
        "directed_controls": [name for name, *_ in controls],
        "related_pair_checks": equivalent_pairs,
        "unrelated_pair_checks": differing_pairs,
        "fixed_basis": {
            "capacity_bound_B": CAPACITY_BOUND,
            "object_names": list(OBJECT_NAMES),
            "persistent_scalar_names": list(SCALAR_NAMES),
            "syntactic_templates": 3,
            "instantiated_tests_per_pair": len(basis),
            "formula": "1 + |R| + 8*B*|O|",
            "pair_test_comparisons": fixed_basis_pair_test_comparisons,
            "single_side_program_executions": fixed_basis_single_side_program_executions,
        },
        "state_dependent_witnesses": {
            "context_comparisons": unrelated_witness_context_checks,
            "single_side_program_executions": witness_single_side_program_executions,
            "lengths": {
                "zero": empty_witnesses,
                "one": one_command_witnesses,
                "two": two_command_witnesses,
                "maximum": 2,
            },
        },
        "all_audit_program_executions": fixed_basis_single_side_program_executions
        + witness_single_side_program_executions
        + 6,
        "all_byte_signature_audit": {
            "byte_values": 256,
            "signature_width_bits": 8,
            "unique_signatures": len(set(byte_signatures.values())),
            "ordered_byte_pair_checks": ordered_byte_pair_checks,
            "unequal_byte_pair_checks": unequal_byte_pair_checks,
            "unequal_byte_pairs_distinguished": unequal_byte_pairs_distinguished,
            "accounting_unit": "direct signature comparisons; not interpreter program executions",
        },
        "byte_2_vs_3_sanity": {
            "equality_to_0_observations_equal": True,
            "equality_to_1_observations_equal": True,
            "fixed_low_bit_probe_distinguishes": True,
            "single_side_program_executions": 6,
        },
        "historical_result_reconciliation": {
            "historical_pair_obligations": 1299,
            "historical_finite_basis_executions": 222,
            "historical_222_scope": "37 related pairs times the former six-test 0/1 basis; pair-level comparisons, not single-side executions",
            "historical_unrelated_witness_context_checks_omitted_from_that_field": 1262,
        },
        "scope": "bounded executable audit; the quantified theorem is the paper proof",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run()
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
