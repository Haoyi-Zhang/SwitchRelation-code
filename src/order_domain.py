"""Finite-byte order constraints used by the branch-certificate producer.

Atoms are input names or literal bytes.  Constraints are equality/strict order
or membership in a finite unary byte domain.  No byte arithmetic is admitted.
The solver uses equality contraction, a DAG, and forward/backward bounds.
"""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
from typing import Any

Atom = int | str
SOLVE_CALLS = 0

@dataclass
class Domain:
    variables: list[str]
    roots: dict[Atom, Atom]
    lower: dict[Atom, int]
    upper: dict[Atom, int]
    reach: dict[Atom, set[Atom]]
    allowed: dict[Atom, int]

    def compare(self, a: Atom, b: Atom) -> int | None:
        x, y = self.roots[a], self.roots[b]
        if x == y:
            return 0
        if y in self.reach[x] or self.upper[x] < self.lower[y]:
            return -1
        if x in self.reach[y] or self.upper[y] < self.lower[x]:
            return 1
        if self.lower[x] == self.upper[x] == self.lower[y] == self.upper[y]:
            return 0
        return None

    def minimum(self) -> list[int]:
        return [self.lower[self.roots[x]] for x in self.variables]


def solve(variables: list[str], constants: list[int], facts: list[list[Any]]) -> Domain | None:
    """Return the coordinatewise least model, or None for an empty domain."""
    global SOLVE_CALLS
    SOLVE_CALLS += 1
    atoms: list[Atom] = list(variables) + list(dict.fromkeys(constants + [0, 128, 255]))
    parent = {x: x for x in atoms}
    def root(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for f in facts:
        if f[0] == 'cmp' and f[2] == 0:
            a, b = root(f[1]), root(f[3])
            parent[b] = a
    roots = {x: root(x) for x in atoms}
    nodes = list(dict.fromkeys(roots.values()))
    allowed = dict.fromkeys(nodes, (1 << 256) - 1)
    lo, hi = dict.fromkeys(nodes, 0), dict.fromkeys(nodes, 255)
    edges = {x: set() for x in nodes}
    for c in constants + [0, 128, 255]:
        r = roots[c]
        allowed[r] &= 1 << c
    for f in facts:
        if f[0] == 'unary':
            r = roots[f[1]]
            keep = sum(1 << x for x in range(256) if int((x & f[2]) == f[3]) == f[4])
            allowed[r] &= keep
        elif f[0] == 'interval':
            r = roots[f[1]]
            allowed[r] &= ((1 << (f[3]+1)) - 1) ^ ((1 << f[2]) - 1)
        elif f[2]:
            a, b = roots[f[1]], roots[f[3]]
            if f[2] == 1:
                a, b = b, a
            if a == b:
                return None
            edges[a].add(b)
    def least_ge(bits, value):
        if value > 255:
            return 256
        tail = bits >> max(value, 0)
        return (tail & -tail).bit_length()-1 + max(value, 0) if tail else 256
    def greatest_le(bits, value):
        if value < 0:
            return -1
        return (bits & ((1 << (value+1))-1)).bit_length()-1
    for x in nodes:
        if not allowed[x]:
            return None
        lo[x], hi[x] = least_ge(allowed[x], 0), greatest_le(allowed[x], 255)
    degree = {x: 0 for x in nodes}
    for targets in edges.values():
        for v in targets:
            degree[v] += 1
    todo = deque(x for x in nodes if degree[x] == 0)
    order = []
    while todo:
        x = todo.popleft()
        order.append(x)
        for y in edges[x]:
            lo[y] = least_ge(allowed[y], max(lo[y], lo[x] + 1))
            degree[y] -= 1
            if degree[y] == 0:
                todo.append(y)
    if len(order) != len(nodes):
        return None
    reach = {x: set() for x in nodes}
    for x in reversed(order):
        for y in edges[x]:
            hi[x] = greatest_le(allowed[x], min(hi[x], hi[y] - 1))
            reach[x].add(y)
            reach[x].update(reach[y])
    if any(lo[x] > hi[x] for x in nodes):
        return None
    return Domain(variables, roots, lo, hi, reach, allowed)


def mask_intervals(mask: int, equal: int) -> list[list[int]]:
    ranges = []
    low = 0
    old = (0 & mask) == equal
    for value in range(1, 256):
        current = (value & mask) == equal
        if current != old:
            ranges.append([low, value - 1])
            low, old = value, current
    ranges.append([low, 255])
    return ranges
