"""Owned scaling schemas fixed before the final certificate campaign."""
from __future__ import annotations
import copy
from make_cases import i, read, length, emit, case, build as small_cases


def build():
    cases = []
    for m in (8, 16, 24, 32):
        variables = ['v'+str(j) for j in range(m)]
        a = ['@'+v for v in variables] + [0] + [1]*(63-m)
        switch = [i('switch', buf='a')]
        p = [length(), emit()]
        cases.append(case('long_length', variables, {'a': a}, p, switch+p))
        p = [length(), emit()]
        q = switch+[i('strchr', buf='a', off=0, char=0, out='n'), emit()]
        cases.append(case('length_as_search', variables, {'a': a}, p, q))
        p = [i('strcpy', src='a', so=0, dst='b', do=0), length('b'), emit()]
        q = switch+[i('switch', buf='b')]+p
        cases.append(case('long_copy', variables, {'a': a, 'b': [1]*64}, p, q))
        pre = [length(out='old'), i('store', buf='a', off='$old', value=1),
               i('scalar', fn='add', left='$old', right=1, width=8, out='next'),
               i('store', buf='a', off='$next', value=0)]
        p = pre+[length(), emit()]
        q = switch+copy.deepcopy(pre)+[i('const', value='$next', out='n'), emit()]
        cases.append(case('bounded_extension', variables, {'a': a}, p, q))
        p = [i('mask_eq', value=read('a'), mask=1, equal=0, out='g'),
             i('assume', value='$g'), length(), emit()]
        cases.append(case('long_parity_mask', variables, {'a': a}, p, switch+p))
        tail = [0]+['@'+v for v in variables]+[0]+[1]*(62-m)
        p = [i('store', buf='a', off=0, value=1), length(),
             i('scalar_lt', left=1, right='$n', out='g'), i('assume', value='$g'), emit(1)]
        q = [i('erase_tail', buf='a')]+p
        cases.append(case('long_tail_feasibility', variables, {'a': tail}, p, q, 'different'))
    for total in (8, 16, 24, 32):
        n = total//2
        variables = ['a'+str(j) for j in range(n)] + ['b'+str(j) for j in range(n)]
        memory = {'a': ['@a'+str(j) for j in range(n)]+[0]+[1]*(63-n),
                  'b': ['@b'+str(j) for j in range(n)]+[0]+[1]*(63-n)}
        p = [i('strcmp', a='a', ao=0, b='b', bo=0, out='n'), emit()]
        q = [i('switch', buf='a'), i('switch', buf='b')]+p
        cases.append(case('long_compare', variables, memory, p, q))
    offset = len(small_cases())
    for k, c in enumerate(cases, offset+1):
        c['id'] = f'C{k:03d}'
    return cases


def fanout_case():
    # Thirty-one independent comparison observations have exponentially many
    # leaves. This is an admitted syntax case but a deliberate budget failure.
    variables = ['v'+str(j) for j in range(32)]
    p = []
    for j in range(31):
        p += [i('byte_lt', left=read('a',j), right=read('a',j+1), out='g'), emit('$g')]
    c = case('comparison_fanout', variables, {'a':['@'+v for v in variables]}, p)
    c['id'] = f'C{len(small_cases())+len(build())+1:03d}'
    return c
