from __future__ import annotations
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contextual import (  # noqa: E402
    ObjectState,
    State,
    StateError,
    allocation_equivalent,
    distinguishing_continuation,
    fixed_complete_basis,
    run_basis_continuation,
)


class ContextualBasisTests(unittest.TestCase):
    def test_fixed_basis_count(self):
        basis = fixed_complete_basis(("b",), ("r",), 2)
        self.assertEqual(len(basis), 1 + 1 + 8 * 2 * 1)

    def test_two_and_three_defeat_zero_one_equalities_but_not_bit_basis(self):
        two = State({"b": ObjectState((2,), (True,))}, {"r": 0})
        three = State({"b": ObjectState((3,), (True,))}, {"r": 0})
        for constant in (0, 1):
            probe = [
                {"op": "byte_eq", "left": {"read": ["b", 0]}, "right": constant, "out": "z"},
                {"op": "emit", "value": "$z"},
            ]
            self.assertEqual(run_basis_continuation(two, probe), run_basis_continuation(three, probe))
        low_bit = [
            {"op": "mask_eq", "value": {"read": ["b", 0]}, "mask": 1, "equal": 1, "out": "z"},
            {"op": "emit", "value": "$z"},
        ]
        self.assertNotEqual(run_basis_continuation(two, low_bit), run_basis_continuation(three, low_bit))

    def test_state_dependent_witness_remains_two_commands(self):
        two = State({"b": ObjectState((2,), (True,))}, {"r": 0})
        three = State({"b": ObjectState((3,), (True,))}, {"r": 0})
        witness = distinguishing_continuation(two, three)
        self.assertIsNotNone(witness)
        self.assertEqual(len(witness), 2)
        self.assertNotEqual(run_basis_continuation(two, witness), run_basis_continuation(three, witness))

    def test_local_cannot_shadow_persistent_register(self):
        state = State({"b": ObjectState((0,), (True,))}, {"r": 7})
        program = [
            {"op": "byte_eq", "left": {"read": ["b", 0]}, "right": 0, "out": "r"},
            {"op": "emit", "value": "$r"},
        ]
        with self.assertRaises(StateError):
            run_basis_continuation(state, program)

    def test_capacity_is_state_data_not_interface_name(self):
        short = State({"b": ObjectState((0,), (True,))}, {"r": 0})
        long = State({"b": ObjectState((0, 0), (True, True))}, {"r": 0})
        self.assertFalse(allocation_equivalent(short, long))
        witness = distinguishing_continuation(short, long)
        self.assertEqual(len(witness), 2)
        self.assertNotEqual(run_basis_continuation(short, witness), run_basis_continuation(long, witness))


if __name__ == "__main__":
    unittest.main()
