"""Portable exact-domain regression; no timing or retained evidence writes."""
from pathlib import Path
import copy
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import order_domain
import branch_producer
import branch_replay
import check_regions
import strict_json


def snapshot():
    rows = []
    for i in range(1, 167):
        case = branch_replay.load(ROOT / 'cases' / f'C{i:03}.json')
        p0, r0 = order_domain.SOLVE_CALLS, branch_replay.DOMAIN_CALLS
        proof = branch_producer.certify(case)
        checked = branch_replay.check(case, proof)
        retained = branch_replay.load(ROOT / 'certificates' / 'branch' / f'C{i:03}.json')
        if proof != retained or checked['verdict'] != case['expected']:
            raise AssertionError('complete certificate mismatch: ' + case['id'])
        rows.append({'proof': proof, 'checked': checked,
                     'producer_calls': order_domain.SOLVE_CALLS-p0,
                     'replayer_calls': branch_replay.DOMAIN_CALLS-r0})
    case = branch_replay.load(ROOT / 'cases' / 'C167.json')
    p0 = order_domain.SOLVE_CALLS
    try:
        branch_producer.certify(case)
    except branch_producer.Rejected as error:
        if str(error) != 'branch node budget':
            raise
        cap = {'reason': str(error), 'producer_calls': order_domain.SOLVE_CALLS-p0}
    else:
        raise AssertionError('C167 unexpectedly completed')
    return {'rows': rows, 'cap': cap, 'regions': check_regions.run(384, 20260915)}


class UnaryBitmapTests(unittest.TestCase):
    def test_literal_all_byte_predicates_and_eviction(self):
        full = (1 << 256)-1
        cache = order_domain._cached_unary_bitmap
        cache.cache_clear()
        # Test-local independent literal byte enumeration grouped by masked value.
        for mask in range(256):
            groups = [[] for _ in range(256)]
            for byte in range(256):
                groups[byte & mask].append(byte)
            for equal in range(256):
                expected = int(''.join('1' if x in groups[equal] else '0'
                                       for x in reversed(range(256))), 2)
                self.assertEqual(order_domain._unary_bitmap(mask, equal, 1), expected)
                self.assertEqual(order_domain._unary_bitmap(mask, equal, 0), full ^ expected)
        self.assertEqual(cache.cache_info().maxsize, 128)
        self.assertLessEqual(cache.cache_info().currsize, 128)
        # Warm reuse, then unrelated predicates evict without state leakage.
        first = order_domain._unary_bitmap(1, 1, 1)
        for mask in range(200):
            order_domain._unary_bitmap(mask, mask, 1)
        self.assertEqual(order_domain._unary_bitmap(1, 1, 1), first)
        facts = [['unary', 'x', 1, 1, 1], ['cmp', 'x', -1, 'y']]
        p0 = order_domain.SOLVE_CALLS
        a = order_domain.solve(['x', 'y'], [], facts)
        b = order_domain.solve(['x', 'y'], [], facts)
        self.assertEqual(order_domain.SOLVE_CALLS-p0, 2)
        self.assertIsNot(a, b)
        self.assertEqual(a.minimum(), [1, 2])
        a.allowed[a.roots['x']] = 0
        self.assertNotEqual(a.allowed, b.allowed)
        self.assertIsNone(order_domain.solve(['x'], [], [['unary', 'x', 1, 2, 1]]))
        self.assertEqual(order_domain.solve(['x'], [], [['unary', 'x', 1, 2, 0]]).minimum(), [0])
        for truth in (False, 1.0):
            self.assertEqual(order_domain._unary_bitmap(1, 1, truth),
                             order_domain._literal_unary_bitmap(1, 1, truth))
        with self.assertRaises(TypeError):
            order_domain._unary_bitmap([], 0, 1)

    def test_complete_current_certificates_counters_and_cap(self):
        result = snapshot()
        rows = result['rows']
        self.assertEqual(sum(len(r['proof']['nodes']) for r in rows), 9986)
        self.assertEqual(sum(r['proof']['leaves'] for r in rows), 6281)
        self.assertEqual(sum(r['proof']['closed_branches'] for r in rows), 1281)
        self.assertEqual(sum(r['producer_calls'] for r in rows), 11267)
        self.assertEqual(sum(r['replayer_calls'] for r in rows), 11267)
        self.assertEqual(result['cap'], {'reason': 'branch node budget', 'producer_calls': 6055})
        self.assertEqual(result['regions']['region_instances'], 384)

    def test_independent_replayer_rejects_all_retained_mutation_kinds(self):
        case = branch_replay.load(ROOT / 'cases' / 'C001.json')
        proof = branch_producer.certify(case)
        split = next(i for i, n in enumerate(proof['nodes']) if n['kind'] == 'split')
        leaf = next(i for i, n in enumerate(proof['nodes']) if n['kind'] == 'leaf')
        child = next(i for i, c in enumerate(proof['nodes'][split]['children']) if type(c) is int)
        changes = [
            lambda p: p['statement'].__setitem__('id', 'changed'),
            lambda p: p.__setitem__('verdict', 'different'),
            lambda p: p.__setitem__('least_input', [255]*len(case['variables'])),
            lambda p: p.__setitem__('leaves', p['leaves']+1),
            lambda p: p.__setitem__('closed_branches', p['closed_branches']+1),
            lambda p: p.__setitem__('max_predicates', p['max_predicates']+1),
            lambda p: p['feasibility'].__setitem__('verdict', 'different_inputs'),
            lambda p: p.__setitem__('leaves', 1.0),
            lambda p: p.__setitem__('closed_branches', True),
            lambda p: p['nodes'][leaf].__setitem__('left', ['accept', [987654321]]),
            lambda p: p['nodes'][leaf].__setitem__('minimum', [255]*len(case['variables'])),
            lambda p: p['nodes'][split].__setitem__('query', ['cmp', 0, 0]),
            lambda p: p['nodes'][split]['children'].__setitem__(child, None),
            lambda p: p['nodes'][split]['children'].__setitem__(child, split),
            lambda p: p['nodes'].append(copy.deepcopy(p['nodes'][leaf])),
            lambda p: p['nodes'].pop(),
        ]
        for i, change in enumerate(changes):
            mutant = copy.deepcopy(proof)
            change(mutant)
            with self.subTest(mutation=i), self.assertRaises(branch_replay.Invalid):
                branch_replay.check(case, mutant)
        for text in ('{"a":1,"a":2}', '{"a":NaN}'):
            with self.assertRaises(strict_json.StrictJSONError):
                strict_json.loads_strict(text)


if __name__ == '__main__':
    unittest.main()
