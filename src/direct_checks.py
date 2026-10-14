"""Exhaust bounded own-model assignments against already checked certificates.

Three deterministic concrete implementations are compared. There is no native
C executable, solver call, network operation or addition to the frozen ledger.
"""
import argparse
import itertools
import json
import os
from pathlib import Path
import platform
import sys
import threading
import time
import branch_replay
import producer
import replay
from scientific_checks import digest

ROOT = Path(__file__).resolve().parents[1]


def checked_pair(case, values):
    results = []
    for key in ('reference', 'candidate'):
        program = case[key]
        direct = replay.interpret(case, values, program)
        for strings in (False, True):
            if producer.Machine(case, values, strings=strings).run(program) != direct:
                raise ValueError('concrete implementation mismatch: ' + case['id'])
        results.append(direct)
    return results


def run(certificates, output):
    output = output.resolve()
    if output == ROOT or ROOT in output.parents or output in ROOT.parents:
        raise ValueError('evidence directory must be outside the artifact')
    output.mkdir(parents=True, exist_ok=False)
    before = digest()
    start, cpu = time.monotonic(), time.process_time()
    timer = threading.Timer(120, lambda: os._exit(124))
    timer.daemon = True
    timer.start()
    records, leaves = [], 0
    try:
        for index in range(1, 167):
            name = f'C{index:03d}'
            case = branch_replay.load(ROOT/'cases'/(name+'.json'))
            proof = branch_replay.load(certificates/(name+'.json'))
            replay.inspect_statement(case)
            if proof['statement'] != case:
                raise ValueError('certificate statement mismatch: ' + name)
            for node in proof['nodes']:
                if node['kind'] == 'leaf':
                    # This is two additional direct executions per leaf; the
                    # full assignment loop separately uses all three paths.
                    values = tuple(node['minimum'])
                    left = replay.interpret(case, values, case['reference'])
                    right = replay.interpret(case, values, case['candidate'])
                    if left != node['left'] or right != node['right']:
                        raise ValueError('leaf observation mismatch: ' + name)
                    leaves += 1
            width = len(case['variables'])
            if width > 1 and not (width == 2 and proof['verdict'] == 'different'):
                continue
            least = acceptance_least = None
            reference_sat = candidate_sat = False
            count = 0
            for values in itertools.product(range(256), repeat=width):
                left, right = checked_pair(case, values)
                count += 1
                reference_sat |= left[0] == 'accept'
                candidate_sat |= right[0] == 'accept'
                if left != right and least is None:
                    least = list(values)
                if (left[0] == 'accept') != (right[0] == 'accept') and acceptance_least is None:
                    acceptance_least = list(values)
            expected_feasibility = {'reference': 'sat' if reference_sat else 'unsat',
                'candidate': 'sat' if candidate_sat else 'unsat',
                'verdict': 'same_inputs' if acceptance_least is None else 'different_inputs',
                'least_input': acceptance_least}
            if (proof['least_input'] != least or proof['feasibility'] != expected_feasibility
                or proof['verdict'] != ('equivalent' if least is None else 'different')):
                raise ValueError('complete-domain result mismatch: ' + name)
            records.append({'id': name, 'variables': width, 'assignments': count,
                            'least_input': least, 'feasibility': expected_feasibility})
            with (output/'cases.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(records[-1], sort_keys=True)+'\n')
        assignments = sum(row['assignments'] for row in records)
        groups = {width: sum(row['variables'] == width for row in records) for width in (0, 1, 2)}
        if groups != {0: 7, 1: 52, 2: 7} or assignments != 472071 or leaves != 6281:
            raise ValueError('direct finite inventory differs from declared selection')
        after = digest()
        if before != after:
            raise ValueError('artifact changed during direct check')
        report = {'status': 'pass', 'cases_by_width': groups,
                  'assignments': assignments, 'leaf_minima_checked': leaves,
                  'single_side_executions': 6*assignments+2*leaves,
                  'regional_solver_obligations': 0,
                  'input_tree_sha256_before': before, 'input_tree_sha256_after': after,
                  'certificates': str(certificates.resolve()),
                  'platform': platform.platform(), 'python': sys.version,
                  'wall_seconds': time.monotonic()-start,
                  'process_cpu_seconds': time.process_time()-cpu,
                  'wall_limit_seconds': 120, 'peak_rss_measured': False,
                  'scope': 'Own bounded model; zero/one-origin cases and two-origin differing cases; no full-domain claim for the other multi-origin cases'}
        (output/'summary.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(report), flush=True)
        return report
    finally:
        timer.cancel()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--certificates', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    run(args.certificates, args.output_dir)
