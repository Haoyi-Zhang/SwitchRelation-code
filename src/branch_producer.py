"""Owned symbolic trace explorer producing complete finite decision certificates.

Byte origins are input atoms or constants. Scalar results become concrete after
all relevant byte comparisons have been decided. Array/word storage is explicit;
this is not an SMT solver or a C frontend.
"""
from __future__ import annotations
from typing import Any
from producer import validate, Rejected
from order_domain import solve

class Split(Exception):
    def __init__(self, query, choices, domains):
        self.query, self.choices, self.domains = query, choices, domains

class Halt(Exception):
    pass

class Oracle:
    def __init__(self, case, constants, facts, domain):
        self.case, self.constants, self.facts, self.domain = case, constants, facts, domain
        self.answers = {}
    def cmp(self, a, b):
        key = ('cmp', a, b)
        if key in self.answers:
            return self.answers[key]
        known = self.domain.compare(a, b)
        if known is not None:
            return known
        choices = [-1, 0, 1]
        domains = [solve(self.case['variables'], self.constants, self.facts + [['cmp', a, r, b]]) for r in choices]
        alive = [r for r, d in zip(choices, domains) if d is not None]
        if len(alive) == 1:
            self.answers[key] = alive[0]
            return alive[0]
        raise Split(['cmp', a, b], choices, domains)
    def mask(self, a, mask, equal):
        r = self.domain.roots[a]
        low, high = self.domain.lower[r], self.domain.upper[r]
        allowed = self.domain.allowed[r]
        results = {int((x & mask) == equal) for x in range(low, high+1) if (allowed >> x) & 1}
        if len(results) == 1:
            return next(iter(results))
        choices = [0, 1]
        domains = [solve(self.case['variables'], self.constants, self.facts + [['unary', a, mask, equal, truth]]) for truth in choices]
        alive = [truth for truth, d in zip(choices, domains) if d is not None]
        if len(alive) == 1:
            return alive[0]
        raise Split(['mask', a, mask, equal], choices, domains)

class SymbolicMachine:
    def __init__(self, case, oracle):
        self.oracle = oracle
        self.memory = {b: [v[1:] if isinstance(v, str) else v for v in buf] for b, buf in case['buffers'].items()}
        self.registers, self.cache, self.output = {}, {}, []
    def number(self, x):
        return self.registers[x[1:]] if isinstance(x, str) else x
    def check_span(self, b, offset, size=1):
        if offset < 0 or size < 0 or offset + size > len(self.memory[b]):
            raise Halt('bounds')
    def read(self, b, offset):
        self.check_span(b, offset)
        value = self.memory[b][offset]
        if value is None:
            raise Halt('uninitialized')
        return value
    def byte(self, value):
        return self.read(value['read'][0], self.number(value['read'][1])) if isinstance(value, dict) else value
    def write(self, b, offset, values, stale=False):
        self.check_span(b, offset, len(values))
        old = self.memory[b]
        if isinstance(old, tuple):
            self.memory[b] = old[:offset] + tuple(values) + old[offset + len(values):]
        else:
            old[offset:offset + len(values)] = values
        if not stale:
            self.cache = {k: v for k, v in self.cache.items() if k[0] != b}
    def terminator(self, b, offset):
        self.check_span(b, offset)
        for pos in range(offset, len(self.memory[b])):
            if self.oracle.cmp(self.read(b, pos), 0) == 0:
                return pos
        raise Halt('unterminated')
    def no_overlap(self, d, start, size, s, off, n):
        if d == s and max(start, off) < min(start + size, off + n):
            raise Halt('overlap')
    def run(self, program):
        try:
            for op in program:
                name, value = op['op'], None
                if name in ('strlen', 'strlen_cached', 'strlen_capacity'):
                    b, pos = op['buf'], self.number(op['off'])
                    key = (b, pos)
                    if name == 'strlen_cached' and key in self.cache:
                        value = self.cache[key]
                    else:
                        try:
                            value = self.terminator(b, pos) - pos
                        except Halt as err:
                            if name != 'strlen_capacity' or str(err) != 'unterminated':
                                raise
                            value = len(self.memory[b]) - pos
                        if name == 'strlen_cached':
                            self.cache[key] = value
                elif name in ('strchr', 'strchr_no_zero'):
                    b, start, c = op['buf'], self.number(op['off']), self.byte(op['char'])
                    end = self.terminator(b, start)
                    value = -1
                    for pos in range(start, end + (name == 'strchr')):
                        if self.oracle.cmp(self.read(b, pos), c) == 0:
                            value = pos - start
                            break
                elif name in ('strcmp', 'strcmp_signed'):
                    a, b = op['a'], op['b']
                    p, q = self.number(op['ao']), self.number(op['bo'])
                    e, f = self.terminator(a, p), self.terminator(b, q)
                    value = 0
                    for j in range(min(e-p, f-q) + 1):
                        x, y = self.read(a, p+j), self.read(b, q+j)
                        if name == 'strcmp_signed':
                            sx = self.oracle.cmp(x, 128) >= 0
                            sy = self.oracle.cmp(y, 128) >= 0
                            value = (-1 if sx else 1) if sx != sy else self.oracle.cmp(x, y)
                        else:
                            value = self.oracle.cmp(x, y)
                        if value != 0 or self.oracle.cmp(x, 0) == 0:
                            break
                elif name in ('store', 'store_stale'):
                    self.write(op['buf'], self.number(op['off']), [self.byte(op['value'])], name == 'store_stale')
                elif name in ('memmove', 'move_forward'):
                    s, d = op['src'], op['dst']
                    p, q, n = self.number(op['so']), self.number(op['do']), self.number(op['n'])
                    self.check_span(s, p, n)
                    self.check_span(d, q, n)
                    snapshot = [self.read(s, p+j) for j in range(n)]
                    if name == 'memmove':
                        self.write(d, q, snapshot)
                    else:
                        for j in range(n):
                            self.write(d, q+j, [self.read(s, p+j)])
                elif name in ('strcpy', 'copy_no_zero', 'strcat'):
                    s, d = op['src'], op['dst']
                    p, q = self.number(op['so']), self.number(op['do'])
                    end = self.terminator(s, p)
                    size = end-p+1
                    start = self.terminator(d, q) if name == 'strcat' else q
                    self.check_span(d, start, size)
                    self.no_overlap(d, q, start-q+size, s, p, size)
                    data = [self.read(s, p+j) for j in range(size - (name == 'copy_no_zero'))]
                    self.write(d, start, data)
                elif name == 'switch':
                    b = op['buf']
                    self.memory[b] = tuple(self.memory[b])
                elif name == 'erase_tail':
                    b = op['buf']
                    end = self.terminator(b, 0)
                    for pos in range(end+1, len(self.memory[b])):
                        if self.memory[b][pos] is not None:
                            self.write(b, pos, [0])
                elif name == 'mask_eq':
                    value = self.oracle.mask(self.byte(op['value']), op['mask'], op['equal'])
                elif name in ('byte_eq', 'byte_lt'):
                    relation = self.oracle.cmp(self.byte(op['left']), self.byte(op['right']))
                    value = int(relation == 0 if name == 'byte_eq' else relation == -1)
                elif name in ('scalar_eq', 'scalar_lt'):
                    a, b = self.number(op['left']), self.number(op['right'])
                    value = int(a == b if name == 'scalar_eq' else a < b)
                elif name == 'scalar':
                    width = op['width']
                    bits = (1 << width) - 1
                    a, b = self.number(op['left']) & bits, self.number(op['right']) & bits
                    fn = op['fn']
                    if fn == 'add': value = (a+b) & bits
                    elif fn == 'sub': value = (a-b) & bits
                    elif fn == 'and': value = a & b
                    elif fn == 'or': value = a | b
                    elif fn == 'xor': value = a ^ b
                    elif fn == 'shl': value = 0 if b >= width else (a << b) & bits
                    else: value = 0 if b >= width else a >> b
                elif name == 'const':
                    value = self.number(op['value'])
                elif name == 'assume':
                    if self.number(op['value']) == 0:
                        return ['reject', self.output]
                elif name == 'emit':
                    self.output.append(self.number(op['value']))
                else:
                    raise Rejected('unsupported symbolic operation')
                if 'out' in op:
                    self.registers[op['out']] = value
            return ['accept', self.output]
        except Halt as err:
            return ['fault', str(err), self.output]


def fact_for(query, choice):
    return ['cmp', query[1], choice, query[2]] if query[0] == 'cmp' else ['unary', query[1], query[2], query[3], choice]


def certify(case: dict[str, Any], max_nodes=6000, max_facts=48):
    constants, _, _ = validate(case, max_variables=32)
    constants = sorted(set(constants + [128, 255]))
    start = solve(case['variables'], constants, [])
    if start is None:
        raise Rejected('empty initial byte domain')
    nodes = []
    least = None
    acceptance_witness = None
    reference_sat = candidate_sat = False
    pending = [(None, None, [], start)]
    maximum_depth = 0
    closed = 0
    leaves = 0
    while pending:
        parent, branch, facts, domain = pending.pop()
        if len(nodes) >= max_nodes:
            raise Rejected('branch node budget')
        index = len(nodes)
        nodes.append(None)
        if parent is not None:
            nodes[parent]['children'][branch] = index
        oracle = Oracle(case, constants, facts, domain)
        try:
            left = SymbolicMachine(case, oracle).run(case['reference'])
            right = SymbolicMachine(case, oracle).run(case['candidate'])
            model = domain.minimum()
            nodes[index] = {'kind': 'leaf', 'left': left, 'right': right, 'minimum': model}
            leaves += 1
            reference_sat |= left[0] == 'accept'
            candidate_sat |= right[0] == 'accept'
            if (left[0] == 'accept') != (right[0] == 'accept'):
                if acceptance_witness is None or model < acceptance_witness:
                    acceptance_witness = model
            if left != right and (least is None or model < least):
                least = model
        except Split as split:
            if len(facts) >= max_facts:
                raise Rejected('branch predicate budget')
            nodes[index] = {'kind': 'split', 'query': split.query, 'choices': split.choices, 'children': [None] * len(split.choices)}
            maximum_depth = max(maximum_depth, len(facts) + 1)
            for k in reversed(range(len(split.choices))):
                d = split.domains[k]
                if d is None:
                    closed += 1
                else:
                    pending.append((index, k, facts + [fact_for(split.query, split.choices[k])], d))
    return {'statement': case, 'nodes': nodes, 'verdict': 'different' if least is not None else 'equivalent', 'least_input': least, 'closed_branches': closed, 'leaves': leaves, 'max_predicates': maximum_depth, 'feasibility': {'reference': 'sat' if reference_sat else 'unsat', 'candidate': 'sat' if candidate_sat else 'unsat', 'verdict': 'same_inputs' if acceptance_witness is None else 'different_inputs', 'least_input': acceptance_witness}}
