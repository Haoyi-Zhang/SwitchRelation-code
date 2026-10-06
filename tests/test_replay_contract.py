from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import branch_replay
import replay
import strict_json
from contextual import ObjectState, State, run_basis_continuation


class ReplayContractTests(unittest.TestCase):
    def test_cli_loader_uses_shared_bounded_kernel(self):
        path = ROOT / "cases" / "C001.json"
        with patch("strict_json.load_strict", wraps=strict_json.load_strict) as loader:
            case = branch_replay.load(path)
        loader.assert_called_once_with(path, max_bytes=64*1024*1024, max_depth=256)
        self.assertEqual(case["id"], "C001")

    def test_small_owned_loader_controls(self):
        controls = [
            '[1]',
            '{"a":1,"a":2}',
            '{"a":NaN}',
            '{"a":' + '[' * 257 + '0' + ']' * 257 + '}',
        ]
        for data in controls:
            with self.subTest(length=len(data)), \
                    patch.object(Path, "stat", return_value=SimpleNamespace(st_size=len(data))), \
                    patch.object(Path, "read_text", return_value=data):
                with self.assertRaises(replay.Invalid):
                    branch_replay.load(Path("owned-control.json"))

    def test_semantic_values_reject_booleans_and_floats_globally(self):
        for value in (True, False, 1.0):
            with self.subTest(value=value), self.assertRaises(replay.Invalid):
                replay.exact_json({"nested": [value]})
        replay.exact_json({"nested": [0, 1, None]})

    def test_retained_certificate_still_replays(self):
        case = branch_replay.load(ROOT / "cases" / "C001.json")
        proof = branch_replay.load(ROOT / "certificates" / "branch" / "C001.json")
        self.assertEqual(branch_replay.check(case, proof)["verdict"], "equivalent")

    def test_local_reassignment_preserves_equal_results(self):
        state = State({"b": ObjectState((3,), (True,))}, {"r": 7})
        program = [
            {"op": "byte_eq", "left": {"read": ["b", 0]}, "right": 3, "out": "t"},
            {"op": "byte_eq", "left": {"read": ["b", 0]}, "right": 2, "out": "t"},
            {"op": "emit", "value": "$t"},
            {"op": "emit", "value": "$r"},
        ]
        self.assertEqual(run_basis_continuation(state, program), ["accept", [0, 7]])

    def test_entry_cannot_read_a_local_before_assignment(self):
        state = State({"b": ObjectState((0,), (True,))}, {})
        from contextual import StateError
        with self.assertRaises(StateError):
            run_basis_continuation(state, [{"op": "emit", "value": "$t"}])

    def test_carried_live_scalar_remains_observable(self):
        left = State({"b": ObjectState((0,), (True,))}, {"live": 1})
        right = State({"b": ObjectState((0,), (True,))}, {"live": 2})
        program = [{"op": "emit", "value": "$live"}]
        self.assertNotEqual(run_basis_continuation(left, program), run_basis_continuation(right, program))


if __name__ == "__main__":
    unittest.main()
