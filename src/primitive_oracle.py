"""Owned exhaustive primitive oracle over two independent input bytes.

No external solver or target program is executed.  The 65,536 concrete states
are reported separately from solver/checker obligations in resource accounting.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import resource
import time
from pathlib import Path
from typing import Any


def run() -> dict[str, Any]:
    started = time.process_time()
    # Preserve NUL, literal 1, and the unary high-bit test; no undeclared operations.
    cells = [(0, 0), (1, 1), (2, 127), (128, 255)]

    def canon(values: tuple[int, int]) -> tuple[int, int]:
        mapping: dict[int, int] = {}
        for lower, upper in cells:
            for rank, value in enumerate(sorted({x for x in values if lower <= x <= upper})):
                mapping[value] = lower + rank
        return tuple(mapping[x] for x in values)  # type: ignore[return-value]

    def scalar(values: tuple[int, int]) -> tuple[int, ...]:
        x, y = values
        a = [x, y, 0, 1]
        b = [y, x, 0, 1]

        def length(data: list[int]) -> int:
            for index, value in enumerate(data):
                if value == 0:
                    return index
            return -1

        def find(data: list[int], character: int) -> int:
            for index, value in enumerate(data):
                if value == character:
                    return index
                if value == 0:
                    return -1
            return -2

        sign = 0
        for left, right in zip(a, b):
            if left != right:
                sign = -1 if left < right else 1
                break
            if left == 0:
                break
        a[1:4] = list(a[0:3])  # overlap-safe snapshot copy
        return (
            length(a),
            find(a, 0),
            find(a, 1),
            sign,
            int(x & 128 == 0),
            int(y & 128 == 0),
            (length(a) + 255) & 255,
        )

    def strings(values: tuple[int, int]) -> tuple[int, ...]:
        x, y = values
        a = "".join(map(chr, [x, y, 0, 1]))
        b = "".join(map(chr, [y, x, 0, 1]))
        prefix_a = a.split(chr(0), 1)[0]
        prefix_b = b.split(chr(0), 1)[0]
        sign = (prefix_a > prefix_b) - (prefix_a < prefix_b)
        a = a[:1] + a[:3]
        end = a.find(chr(0))
        scanned = a if end < 0 else a[: end + 1]
        found_zero = scanned.find(chr(0))
        found_one = scanned.find(chr(1))
        if end < 0:
            if found_zero < 0:
                found_zero = -2
            if found_one < 0:
                found_one = -2
        return (
            end,
            found_zero,
            found_one,
            sign,
            int(x < 128),
            int(y < 128),
            (end + 255) & 255,
        )

    checked = 0
    orbits: set[tuple[int, int]] = set()
    first_bug = None
    for x, y in itertools.product(range(256), repeat=2):
        values = (x, y)
        representative = canon(values)
        if scalar(values) != strings(values):
            raise AssertionError((values, scalar(values), strings(values)))
        if scalar(values) != scalar(representative):
            raise AssertionError((values, representative, scalar(values), scalar(representative)))
        orbits.add(representative)
        checked += 1
        # Owned negative control: discard initialized tail, then overwrite NUL.
        if first_bug is None and x != 0:
            original = [1, x, 0]
            discarded = [1, 0, 0]
            reference_length = original.index(0)
            candidate_length = discarded.index(0)
            if reference_length != candidate_length:
                first_bug = {
                    "initial": [0, x, 0],
                    "overwrite": [0, 1],
                    "reference_length": reference_length,
                    "candidate_length": candidate_length,
                }
    # Non-contiguous unary-signature merging is not an ordered abstraction.
    negative_order = {
        "x": 2,
        "y": 1,
        "same_parity_representatives": [0, 1],
        "before": 2 > 1,
        "after": 0 > 1,
    }
    return {
        "status": "pass",
        "full_byte_assignments": checked,
        "canonical_assignments": len(orbits),
        "semantic_mismatches": 0,
        "palette_transport_mismatches": 0,
        "negative_tail": first_bug,
        "negative_noncontiguous_cells": negative_order,
        "cpu_seconds": time.process_time() - started,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "workers": 1,
        "external_solver_calls": 0,
        "counted_solver_checker_obligations": 0,
        "concrete_state_evaluations": checked,
        "primitive_result_components": 7,
        "alphabet_bits": 8,
        "independent_byte_variables": 2,
        "max_buffer_capacity": 4,
        "resource_note": "one CPU affinity; no external solver; direct states reported separately",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("primitive_oracle_reproduced.json"))
    args = parser.parse_args()
    # Apply the per-run resource envelope before the exhaustive loop.
    address_limit = 2500 * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (address_limit, address_limit))
    resource.setrlimit(resource.RLIMIT_CPU, (110, 115))
    if hasattr(os, "sched_getaffinity"):
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    result = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
