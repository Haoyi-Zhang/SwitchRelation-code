# Full abstraction and the fixed finite basis

## 1. Exact scope and observation contract

Fix a global capacity bound `B` and a static **name interface** `I=(O,R)`, where
`O` is a finite object-name set and `R` is a finite persistent scalar-register
set.  Capacity is state data: each valid state supplies
`C_sigma(o) in {1,...,B}`.  Two states can therefore have the same static name
interface while having different capacities.

A continuation may read persistent registers and bind fresh scalar temporaries
from a disjoint namespace `T`.  Every result binder is in `T`, no binder shadows
`R`, and locals are discarded at termination.  The terminal observations are
only

```
accept(emissions)
reject(emissions)
fault(tag, emissions)
```

with the first fault tag and the emitted integer sequence.  Final heaps,
persistent stores, local stores, cache maps, and view tags are not returned
directly.  Persistent registers are nevertheless indirectly observable because
a continuation may emit them.  There is no direct byte-output command.

All theorem states satisfy the valid-cache invariant.  A materialized cache entry
must equal the length obtained from the declared scan semantics.  An invalid
(stale) cache is outside the theorem precondition.

## 2. Allocation equivalence

For valid states over the same `(O,R)`, define `sigma ~=A tau` when:

1. corresponding objects have equal capacities;
2. corresponding cells have equal initialization bits;
3. every initialized corresponding cell contains the same byte;
4. persistent scalar registers are equal;
5. prior emitted sequences are equal.

The relation quotients payload bytes below false initialization bits, valid cache
materialization, and the current byte/string view tag.

Contextual equivalence is

```
sigma ~=ctx tau  iff  for every well-typed finite continuation K over (I,B),
                       Obs(K,sigma) = Obs(K,tau).
```

## 3. Primitive preservation

**Lemma 1 (expression agreement).**  From `sigma ~=A tau`, corresponding scalar
expressions evaluate to the same integer.  Corresponding byte expressions either
return the same byte or produce the same exact fault.

**Proof.**  Persistent registers agree and local temporaries are produced by the
same previous commands, so scalar operands agree inductively.  Scalar operators
are deterministic total functions of equal operands.  A byte read uses equal
offsets; equal capacities give the same bounds decision; equal initialization
bits give the same initialization decision; and a successful read returns an
initialized byte equal by clause 3.  QED.

**Lemma 2 (scan agreement).**  Corresponding terminator scans from related states
return the same absolute index or the same first fault.

**Proof.**  Lemma 1 gives equal starts.  The scans visit equal indices under equal
capacities.  At each index the initialization bit and, when initialized, the byte
agree.  Therefore the first zero, first uninitialized cell, or allocation end is
the same.  QED.

**Lemma 3 (cache transparency).**  In valid related states, a cached and uncached
length query produce the same scalar or fault.  Correct writes preserve cache
validity and may leave the two partial cache maps structurally different.

**Proof.**  A present valid entry equals the logical scan length; a missing entry
computes that same length by Lemma 2.  Correct writes invalidate all entries for
the written base.  QED.

**Lemma 4 (one-command simulation).**  Let `c` be the same declared correct
command on both sides.  From valid `sigma ~=A tau`, execution of `c` yields the
same terminal observation, or valid successors related by `~=A` with equal local
results.

**Proof.**  Case analysis follows the declared evaluation order.  Length, search,
and comparison use Lemmas 1--3.  Store evaluates the same source byte, validates
the same destination, writes equal bytes, and invalidates the same base's cache.
Snapshot move reads equal complete source vectors before writes.  Copy and
concatenation obtain equal scan endpoints, capacity checks, overlap decisions,
and written vectors.  Scalar commands are deterministic on equal operands;
`assume` and `emit` therefore agree.  `switch` changes only the quotiented view
tag.  Every result binder is a fresh local on both sides.  QED.

This lemma is about running the **same command** in two related states.  It must
not be confused with refinement equivalence between a reference command and an
alternative command.  Several alternatives used as negative controls (signed
comparison, omitted-NUL search or copy, forward copy, tail erasure, and
capacity-as-length) are deterministic commands and can preserve `~=A` when the
same alternative is run on both related states, while still disagreeing with the
intended reference operation on one initial state.  The stale-cache alternative
is different: a store that retains an old length entry can map a valid state to
an invalid one.  For example, `[1,0]` with cached length 1, followed by a stale
store of 0 at index 0, leaves a cache value 1 although the logical scan length is
0.  It therefore violates the valid-state premise needed for cache transparency.

## 4. Universal sufficiency and maximality

**Theorem 5 (universal sufficiency).**  `sigma ~=A tau` implies
`sigma ~=ctx tau`.

**Proof.**  Induct on an arbitrary finite continuation.  The empty continuation
returns equal status and prior emissions.  Lemma 4 gives either equal termination
or related successors with the same next program point.  Apply the induction
hypothesis.  QED.

## 5. State-dependent short witnesses

**Lemma 6 (constructive distinction).**  If valid states over the same `(O,R)`
are not allocation-equivalent, then a common well-typed continuation of length at
most two has unequal observations.

**Proof.**  Inspect the first failed relation clause in a fixed order.

1. Different prior emissions: choose the empty continuation.
2. Different persistent register `r`: choose `emit r`.
3. Different capacities: let `i` be the smaller capacity.  With a fresh local
   `t`, execute `t := (read(o,i) == 0); emit t`.  The smaller side faults bounds;
   the larger side either faults uninitialized or emits.
4. Different initialization at an in-range cell: the same probe faults
   uninitialized on exactly one side.
5. Different initialized bytes `x != y`: choose the **state-dependent** literal
   `x` and execute `t := (read(o,i) == x); emit t`.  The sides emit 1 and 0.

Locals are not persistent and are erased from the terminal observation.  Cache,
view, and jointly uninitialized payload differences are not relation failures.
QED.

**Corollary 7 (full abstraction and greatest safe relation).**

```
sigma ~=A tau  iff  sigma ~=ctx tau.
```

Every relation safe for all continuations is a subset of `~=A`.

**Proof.**  The forward implication is Theorem 5.  The reverse is the
contrapositive of Lemma 6.  If a relation is safe for all continuations, each
related pair is contextually equivalent and hence allocation-equivalent.  QED.

## 6. State-independent finite complete basis

The length-two witness is not a fixed test family because its byte literal may be
chosen after examining the states.  Define instead, for every object `o`, every
`0 <= i < B`, and every bit `0 <= k < 8`, the fixed probe

```
t := mask_eq(read(o,i), mask=2^k, equal=2^k); emit t
```

with a fresh local `t`.  Let the basis contain:

1. the empty continuation;
2. `emit r` for each persistent register `r`;
3. all fixed bit probes above.

There are three syntactic templates and exactly

```
1 + |R| + 8*B*|O|
```

instantiated tests.  If run test by test, the suite has
`|R| + 16*B*|O|` command occurrences.

**Theorem 8 (finite complete basis).**  Two valid states over the same `(O,R)`
with capacities bounded by `B` are allocation-equivalent iff every basis test has
the same observation.

**Proof.**  The forward direction is Theorem 5.  Conversely, the empty test fixes
prior emissions and scalar tests fix the persistent store.  If capacities differ,
take the smaller capacity `i`: each bit probe at `i` faults bounds on the smaller
side, whereas the larger side either faults uninitialized or emits.  If
initialization differs at a common in-range index, a probe faults uninitialized
on exactly one side.  If both cells are initialized, the eight probe results are
the bits of the byte.  The map

```
b -> (((b & 2^k) == 2^k) for k=0,...,7)
```

is injective on all 256 bytes.  Therefore all retained relation clauses hold.
QED.

A fixed equality basis that tests only literals 0 and 1 is not complete: one-cell
states containing initialized bytes 2 and 3 return the same answers to both tests.
The bit-0 probe returns 0 for 2 and 1 for 3.

## 7. Executable audit and accounting scope

`src/contextual.py` implements the relation, state-dependent witness, fixed basis,
and a probe interpreter with separate persistent/local stores.
`src/check_full_abstraction.py` checks:

- 36 fixed-capacity base states and all `36^2 = 1,296` ordered pairs;
- three additional directed controls: capacity mismatch, initialization mismatch,
  and a related pair differing only in view/cache/uninitialized payload;
- 1,299 total pair classifications, comprising 37 related and 1,262 unrelated;
- the 18-test fixed basis for `B=2`, one object, and one persistent register on
  every pair (`23,382` pair/test comparisons, `46,764` single-side executions);
- all 1,262 state-dependent witnesses (`2,524` single-side executions);
- the explicit byte-2/byte-3 control (six single-side executions).

The resulting post-repair audit has 49,294 single-side program executions.  It is
outside the frozen historical 99,999-obligation ledger.

The earlier `full_abstraction_check.json` field
`finite_basis_executions = 222` had a narrower meaning: 37 related pairs times a
six-test 0/1 basis, counted as pair-level comparisons.  It did not count the
1,262 unrelated-pair witness comparisons, although those witnesses were executed.
The reconciliation record preserves both facts rather than rewriting the original
result file.

This finite audit checks implementations on a selected bounded family.  It does
not replace the quantified proof above or establish a refinement theorem for the
Python implementation.
