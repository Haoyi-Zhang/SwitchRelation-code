"""Small exact oracle for the two independently written region solvers.

Every generated variable is first restricted to {0,1,2,3}.  The script then
brute-forces that finite cube and compares feasibility, the coordinatewise least
model, and all determinate pairwise comparisons with both solver algorithms.
"""
from __future__ import annotations

import argparse
import itertools
import json
import random
from pathlib import Path
from typing import Any

import branch_replay
import order_domain


def satisfies(model: dict[str, int], fact: list[Any]) -> bool:
    def value(atom: int | str) -> int:
        return atom if type(atom) is int else model[atom]

    if fact[0] == "interval":
        return fact[2] <= value(fact[1]) <= fact[3]
    if fact[0] == "unary":
        return int((value(fact[1]) & fact[2]) == fact[3]) == fact[4]
    if fact[0] == "cmp":
        left, relation, right = value(fact[1]), fact[2], value(fact[3])
        actual = -1 if left < right else 1 if left > right else 0
        return actual == relation
    raise AssertionError("unknown fact")


def models(variables: list[str], facts: list[list[Any]]) -> list[tuple[int, ...]]:
    answer = []
    for values in itertools.product(range(4), repeat=len(variables)):
        model = dict(zip(variables, values))
        if all(satisfies(model, fact) for fact in facts):
            answer.append(values)
    return answer


def exact_relation(
    variables: list[str], satisfying: list[tuple[int, ...]], left: int | str, right: int | str
) -> int | None:
    def value(atom: int | str, model: dict[str, int]) -> int:
        return atom if type(atom) is int else model[atom]

    relations = set()
    for values in satisfying:
        model = dict(zip(variables, values))
        a, b = value(left, model), value(right, model)
        relations.add(-1 if a < b else 1 if a > b else 0)
    return next(iter(relations)) if len(relations) == 1 else None


def generated_instances(count: int, seed: int) -> list[tuple[list[str], list[list[Any]]]]:
    rng = random.Random(seed)
    result = []
    # A deterministic prefix covers characteristic corner cases.
    fixed = [
        (["x"], [["interval", "x", 0, 3]]),
        (["x"], [["interval", "x", 0, 3], ["cmp", "x", 0, 2]]),
        (["x"], [["interval", "x", 0, 3], ["cmp", "x", -1, 0]]),
        (["x", "y"], [["interval", "x", 0, 3], ["interval", "y", 0, 3], ["cmp", "x", -1, "y"]]),
        (["x", "y"], [["interval", "x", 0, 3], ["interval", "y", 0, 3], ["cmp", "x", 0, "y"], ["cmp", "x", -1, "y"]]),
        (["x", "y", "z"], [["interval", "x", 0, 3], ["interval", "y", 0, 3], ["interval", "z", 0, 3], ["cmp", "x", -1, "y"], ["cmp", "y", -1, "z"]]),
    ]
    result.extend(fixed[:count])
    while len(result) < count:
        width = rng.choice((1, 2, 3))
        variables = [chr(ord("x") + index) for index in range(width)]
        facts: list[list[Any]] = [["interval", name, 0, 3] for name in variables]
        atoms: list[int | str] = variables + [0, 1, 2, 3]
        for _ in range(rng.randrange(0, 8)):
            kind = rng.choice(("cmp", "cmp", "unary", "interval"))
            if kind == "cmp":
                facts.append(["cmp", rng.choice(atoms), rng.choice((-1, 0, 1)), rng.choice(atoms)])
            elif kind == "unary":
                atom = rng.choice(variables)
                mask = rng.choice((1, 2, 3))
                equal = rng.randrange(4) & mask
                facts.append(["unary", atom, mask, equal, rng.choice((0, 1))])
            else:
                atom = rng.choice(variables)
                lower = rng.randrange(4)
                upper = rng.randrange(lower, 4)
                facts.append(["interval", atom, lower, upper])
        result.append((variables, facts))
    return result


def run(count: int, seed: int) -> dict[str, Any]:
    order_before = order_domain.SOLVE_CALLS
    replay_before = branch_replay.DOMAIN_CALLS
    satisfiable = 0
    unsatisfiable = 0
    brute_assignments = 0
    comparison_checks = 0
    for index, (variables, facts) in enumerate(generated_instances(count, seed)):
        satisfying = models(variables, facts)
        brute_assignments += 4 ** len(variables)
        producer = order_domain.solve(variables, [0, 1, 2, 3], facts)
        replayer = branch_replay.region(variables, facts)
        if not satisfying:
            unsatisfiable += 1
            if producer is not None or replayer is not None:
                raise AssertionError(f"feasibility mismatch at instance {index}")
            continue
        satisfiable += 1
        if producer is None or replayer is None:
            raise AssertionError(f"spurious unsatisfiable result at instance {index}")
        coordinate_minimum = [min(row[column] for row in satisfying) for column in range(len(variables))]
        if tuple(coordinate_minimum) not in satisfying:
            raise AssertionError(f"model family not minimum-closed at instance {index}")
        if producer.minimum() != coordinate_minimum or replayer.minimum() != coordinate_minimum:
            raise AssertionError(f"minimum mismatch at instance {index}")
        atoms: list[int | str] = variables + [0, 1, 2, 3]
        for left in atoms:
            for right in atoms:
                expected = exact_relation(variables, satisfying, left, right)
                comparison_checks += 1
                if producer.compare(left, right) != expected:
                    raise AssertionError(f"producer relation mismatch at instance {index}: {left},{right}")
                if replayer.relation(left, right) != expected:
                    raise AssertionError(f"replayer relation mismatch at instance {index}: {left},{right}")
    producer_calls = order_domain.SOLVE_CALLS - order_before
    replayer_calls = branch_replay.DOMAIN_CALLS - replay_before
    return {
        "status": "pass",
        "seed": seed,
        "region_instances": count,
        "satisfiable": satisfiable,
        "unsatisfiable": unsatisfiable,
        "brute_force_assignments": brute_assignments,
        "pairwise_relation_checks": comparison_checks,
        "producer_solver_calls": producer_calls,
        "replayer_solver_calls": replayer_calls,
        "counted_solver_checker_obligations": producer_calls + replayer_calls + count,
        "alphabet": [0, 1, 2, 3],
        "scope": "finite solver cross-check; not a proof of arbitrary Python execution",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=512)
    parser.add_argument("--seed", type=int, default=20260915)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.count <= 4096:
        raise SystemExit("count must be in 1..4096")
    result = run(args.count, args.seed)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
