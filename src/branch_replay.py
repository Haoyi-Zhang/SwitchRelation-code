"""Independent replayer for finite branch certificates.

This module imports neither explorer nor producer constraint code.  Constraint
consistency uses direct lower/upper relaxation, without equality contraction or
a topological sort.  Operational replay uses list memory throughout; converting
an entire allocation to a word is erased at this logical level.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from replay import Invalid, require, load, inspect_statement, exact_json

DOMAIN_CALLS = 0

class Region:
    def __init__(self, variables, lower, upper, edges, domains):
        self.variables, self.lower, self.upper, self.edges = variables, lower, upper, edges
        self.paths = {}
        self.domains = domains
    def path(self, start, finish, strict):
        key = (start, finish, strict)
        if key in self.paths:
            return self.paths[key]
        todo, visited = [(start, False)], set()
        while todo:
            node, positive = todo.pop()
            if (node, positive) in visited:
                continue
            visited.add((node, positive))
            if node == finish and (positive or not strict):
                self.paths[key] = True
                return True
            for source, target, step in self.edges:
                if source == node:
                    todo.append((target, positive or step > 0))
        self.paths[key] = False
        return False
    def relation(self, a, b):
        if a == b or (self.path(a, b, False) and self.path(b, a, False)):
            return 0
        if self.path(a, b, True) or self.upper[a] < self.lower[b]:
            return -1
        if self.path(b, a, True) or self.upper[b] < self.lower[a]:
            return 1
        if self.lower[a] == self.upper[a] == self.lower[b] == self.upper[b]:
            return 0
        return None
    def minimum(self):
        return [self.lower[v] for v in self.variables]


def region(variables, facts):
    """Exact consistency and coordinatewise least solution of byte order facts."""
    global DOMAIN_CALLS
    DOMAIN_CALLS += 1
    nodes = list(variables) + list(range(256))
    lower = {v: 0 for v in variables}
    upper = {v: 255 for v in variables}
    lower.update({n: n for n in range(256)})
    upper.update({n: n for n in range(256)})
    domains = {v: set(range(256)) for v in variables}
    domains.update({x: {x} for x in range(256)})
    edges = []
    for fact in facts:
        if fact[0] == 'unary':
            atom, mask, equal, truth = fact[1:]
            domains[atom] = {x for x in domains[atom] if int((x & mask) == equal) == truth}
        elif fact[0] == 'interval':
            atom, a, b = fact[1:]
            domains[atom] = {x for x in domains[atom] if a <= x <= b}
        elif fact[2] == 0:
            edges.extend([(fact[1], fact[3], 0), (fact[3], fact[1], 0)])
        elif fact[2] < 0:
            edges.append((fact[1], fact[3], 1))
        else:
            edges.append((fact[3], fact[1], 1))
    for x in nodes:
        if not domains[x]:
            return None
        lower[x], upper[x] = min(domains[x]), max(domains[x])
    # Each successful update removes at least one endpoint value.  There are
    # at most 512*|nodes| endpoint changes; this does not assume convex domains.
    changes = 0
    while changes <= 512*len(nodes):
        changed = False
        for a, b, step in edges:
            if lower[b] < lower[a]+step:
                possibilities = [x for x in domains[b] if x >= lower[a]+step]
                if not possibilities:
                    return None
                lower[b] = min(possibilities)
                changed = True
                changes += 1
            if upper[a] > upper[b]-step:
                possibilities = [x for x in domains[a] if x <= upper[b]-step]
                if not possibilities:
                    return None
                upper[a] = max(possibilities)
                changed = True
                changes += 1
            if lower[a] > upper[a] or lower[b] > upper[b]:
                return None
        if not changed:
            return Region(variables, lower, upper, edges, domains)
    return None

class Question(Exception):
    def __init__(self, query, choices, regions):
        self.query, self.choices, self.regions = query, choices, regions

class PathFault(Exception):
    pass

class Questions:
    def __init__(self, variables, facts, current):
        self.variables, self.facts, self.current = variables, facts, current
        self.cache = {}
    def compare(self, a, b):
        key = (a, b)
        if key in self.cache:
            return self.cache[key]
        answer = self.current.relation(a, b)
        if answer is not None:
            return answer
        choices = [-1, 0, 1]
        children = [region(self.variables, self.facts + [['cmp', a, r, b]]) for r in choices]
        survivors = [r for r, child in zip(choices, children) if child is not None]
        if len(survivors) == 1:
            self.cache[key] = survivors[0]
            return survivors[0]
        raise Question(['cmp', a, b], choices, children)
    def unary(self, atom, mask, equal):
        low, high = self.current.lower[atom], self.current.upper[atom]
        values = self.current.domains[atom]
        possible = {int((x & mask) == equal) for x in values if low <= x <= high}
        if len(possible) == 1:
            return next(iter(possible))
        choices = [0, 1]
        children = [region(self.variables, self.facts + [['unary', atom, mask, equal, truth]]) for truth in choices]
        alive = [choice for choice, child in zip(choices, children) if child is not None]
        if len(alive) == 1:
            return alive[0]
        raise Question(['mask', atom, mask, equal], choices, children)


def execute(case, program, questions):
    """List semantics over immutable input origins; scalars are ordinary integers."""
    heap = {name: [v[1:] if isinstance(v, str) else v for v in data] for name, data in case['buffers'].items()}
    registers, lengths, observed = {}, {}, []
    def num(value):
        return registers[value[1:]] if isinstance(value, str) else value
    def range_check(name, first, count):
        if not (0 <= first and 0 <= count and first+count <= len(heap[name])):
            raise PathFault('bounds')
    def read(name, offset):
        range_check(name, offset, 1)
        answer = heap[name][offset]
        if answer is None:
            raise PathFault('uninitialized')
        return answer
    def byte(value):
        return read(value['read'][0], num(value['read'][1])) if isinstance(value, dict) else value
    def end(name, start):
        range_check(name, start, 1)
        pos = start
        while pos < len(heap[name]):
            if questions.compare(read(name, pos), 0) == 0:
                return pos
            pos += 1
        raise PathFault('unterminated')
    def write(name, first, data, invalidate=True):
        range_check(name, first, len(data))
        for j in range(len(data)):
            heap[name][first+j] = data[j]
        if invalidate:
            for key in list(lengths):
                if key[0] == name:
                    del lengths[key]
    try:
        for command in program:
            opcode, result = command['op'], None
            if opcode in ('strlen', 'strlen_cached', 'strlen_capacity'):
                name, offset = command['buf'], num(command['off'])
                key = (name, offset)
                if opcode == 'strlen_cached' and key in lengths:
                    result = lengths[key]
                else:
                    try:
                        result = end(name, offset) - offset
                    except PathFault as error:
                        if opcode != 'strlen_capacity' or str(error) != 'unterminated':
                            raise
                        result = len(heap[name]) - offset
                    if opcode == 'strlen_cached':
                        lengths[key] = result
            elif opcode in ('strchr', 'strchr_no_zero'):
                name, offset, needle = command['buf'], num(command['off']), byte(command['char'])
                last = end(name, offset)
                result = -1
                for pos in range(offset, last + int(opcode == 'strchr')):
                    if questions.compare(read(name, pos), needle) == 0:
                        result = pos-offset
                        break
            elif opcode in ('strcmp', 'strcmp_signed'):
                x, y = command['a'], command['b']
                i, j = num(command['ao']), num(command['bo'])
                end(x, i)
                end(y, j)
                while True:
                    u, v = read(x, i), read(y, j)
                    if opcode == 'strcmp_signed':
                        negative_u = questions.compare(u, 128) != -1
                        negative_v = questions.compare(v, 128) != -1
                        if negative_u and not negative_v:
                            result = -1
                        elif negative_v and not negative_u:
                            result = 1
                        else:
                            result = questions.compare(u, v)
                    else:
                        result = questions.compare(u, v)
                    if result != 0 or questions.compare(u, 0) == 0:
                        break
                    i, j = i+1, j+1
            elif opcode in ('store', 'store_stale'):
                name, offset, value = command['buf'], num(command['off']), byte(command['value'])
                write(name, offset, [value], opcode != 'store_stale')
            elif opcode in ('memmove', 'move_forward'):
                src, dst = command['src'], command['dst']
                i, j, n = num(command['so']), num(command['do']), num(command['n'])
                range_check(src, i, n)
                range_check(dst, j, n)
                copied = [read(src, i+k) for k in range(n)]
                if opcode == 'memmove':
                    write(dst, j, copied)
                else:
                    for k in range(n):
                        write(dst, j+k, [read(src, i+k)])
            elif opcode in ('strcpy', 'copy_no_zero', 'strcat'):
                src, dst = command['src'], command['dst']
                first, start = num(command['so']), num(command['do'])
                final = end(src, first)
                target = end(dst, start) if opcode == 'strcat' else start
                n = final-first+1
                range_check(dst, target, n)
                if src == dst and set(range(first, final+1)) & set(range(start, target+n)):
                    raise PathFault('overlap')
                data = [read(src, pos) for pos in range(first, final+1)]
                if opcode == 'copy_no_zero':
                    data.pop()
                write(dst, target, data)
            elif opcode == 'switch':
                pass
            elif opcode == 'erase_tail':
                name = command['buf']
                final = end(name, 0)
                for i in range(final+1, len(heap[name])):
                    if heap[name][i] is not None:
                        write(name, i, [0])
            elif opcode == 'mask_eq':
                result = questions.unary(byte(command['value']), command['mask'], command['equal'])
            elif opcode in ('byte_eq', 'byte_lt'):
                sign = questions.compare(byte(command['left']), byte(command['right']))
                result = int(sign == 0 if opcode == 'byte_eq' else sign < 0)
            elif opcode in ('scalar_eq', 'scalar_lt'):
                a, b = num(command['left']), num(command['right'])
                result = int(a == b if opcode == 'scalar_eq' else a < b)
            elif opcode == 'scalar':
                w = command['width']
                modulus = 2**w
                a, b = num(command['left']) % modulus, num(command['right']) % modulus
                function = command['fn']
                if function == 'add': result = (a+b) % modulus
                elif function == 'sub': result = (a-b) % modulus
                elif function == 'and': result = a & b
                elif function == 'or': result = a | b
                elif function == 'xor': result = a ^ b
                elif function == 'shl': result = 0 if b >= w else (a * 2**b) % modulus
                else: result = 0 if b >= w else a // 2**b
            elif opcode == 'const':
                result = num(command['value'])
            elif opcode == 'assume':
                if num(command['value']) == 0:
                    return ['reject', observed]
            elif opcode == 'emit':
                observed.append(num(command['value']))
            else:
                raise Invalid('unknown replay opcode')
            if 'out' in command:
                registers[command['out']] = result
        return ['accept', observed]
    except PathFault as error:
        return ['fault', str(error), observed]


def check(case: dict[str, Any], proof: dict[str, Any]):
    exact_json(case); exact_json(proof)
    fields = set('statement nodes verdict least_input closed_branches leaves max_predicates feasibility'.split())
    require(isinstance(proof, dict) and set(proof) == fields, 'branch certificate fields')
    require(proof['statement'] == case, 'branch statement binding')
    inspect_statement(case, max_variables=32)
    nodes = proof['nodes']
    require(isinstance(nodes, list) and 1 <= len(nodes) <= 6000, 'node budget')
    initial = region(case['variables'], [])
    require(initial is not None, 'initial byte domain')
    pending = [(0, [], initial)]
    visited = set()
    least, closed, leaves, maximum_depth = None, 0, 0, 0
    acceptance_witness = None
    reference_sat = candidate_sat = False
    while pending:
        index, facts, current = pending.pop()
        require(type(index) is int and 0 <= index < len(nodes) and index not in visited, 'node reference or repeated node')
        require(len(facts) <= 48, 'predicate budget')
        visited.add(index)
        node = nodes[index]
        require(isinstance(node, dict), 'node object')
        questions = Questions(case['variables'], facts, current)
        try:
            left = execute(case, case['reference'], questions)
            right = execute(case, case['candidate'], questions)
            require(set(node) == set('kind left right minimum'.split()) and node['kind'] == 'leaf', 'expected leaf')
            require(node['left'] == left and node['right'] == right, 'leaf operational results')
            minimum = current.minimum()
            require(isinstance(node['minimum'], list) and all(type(v) is int for v in node['minimum']) and node['minimum'] == minimum, 'leaf minimum')
            leaves += 1
            reference_sat |= left[0] == 'accept'
            candidate_sat |= right[0] == 'accept'
            if (left[0] == 'accept') != (right[0] == 'accept'):
                if acceptance_witness is None or minimum < acceptance_witness:
                    acceptance_witness = minimum
            if left != right and (least is None or minimum < least):
                least = minimum
        except Question as question:
            require(set(node) == set('kind query choices children'.split()) and node['kind'] == 'split', 'expected split')
            require(node['query'] == question.query and node['choices'] == question.choices, 'split query or partition')
            child_ids = node['children']
            require(isinstance(child_ids, list) and len(child_ids) == len(question.choices), 'branch arity')
            maximum_depth = max(maximum_depth, len(facts)+1)
            for choice, child, child_id in zip(question.choices, question.regions, child_ids):
                if child is None:
                    require(child_id is None, 'nonempty reference for infeasible branch')
                    closed += 1
                else:
                    require(type(child_id) is int, 'missing feasible branch')
                    q = question.query
                    f = ['cmp', q[1], choice, q[2]] if q[0] == 'cmp' else ['unary', q[1], q[2], q[3], choice]
                    pending.append((child_id, facts+[f], child))
    require(len(visited) == len(nodes), 'unreachable certificate nodes')
    verdict = 'equivalent' if least is None else 'different'
    require(proof['verdict'] == verdict and proof['least_input'] == least, 'branch verdict or minimum witness')
    require(proof['closed_branches'] == closed and proof['leaves'] == leaves and proof['max_predicates'] == maximum_depth, 'branch totals')
    feasibility = {'reference': 'sat' if reference_sat else 'unsat', 'candidate': 'sat' if candidate_sat else 'unsat', 'verdict': 'same_inputs' if acceptance_witness is None else 'different_inputs', 'least_input': acceptance_witness}
    require(proof['feasibility'] == feasibility, 'feasibility summary')
    return {'feasibility': feasibility, 'id': case['id'], 'nodes': len(nodes), 'leaves': leaves, 'closed_branches': closed, 'max_predicates': maximum_depth, 'verdict': verdict, 'least_input': least, 'full_domain': 256**len(case['variables'])}

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('case', type=Path)
    p.add_argument('certificate', type=Path)
    args = p.parse_args()
    try:
        before = DOMAIN_CALLS
        result = check(load(args.case), load(args.certificate))
        calls = DOMAIN_CALLS - before
        result['replayer_region_calls'] = calls
        result['top_level_checker_obligations'] = 1
        result['counted_obligations'] = calls + 1
        result['process_isolation'] = 'independent_cli_process'
        print(json.dumps(result, sort_keys=True))
    except (Invalid, KeyError, TypeError, ValueError, RecursionError, OSError) as error:
        raise SystemExit('REJECT: '+str(error))
