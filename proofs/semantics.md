# Declared bounded semantics

This document specifies the model used by the theorem, producer, and replayer.
It is not a formalization of all ISO C or any particular libc.  Capacities are
1--64 cells; there are 1--4 fixed objects, at most 32 independent initial byte
variables, at most 64 commands per side, and at most 48 explicit source predicates
per side.  The adaptive certificate separately admits at most 48 regional facts
on a branch and 6,000 nodes.  Source predicates and regional facts are different
quantities.  Hitting a limit yields `UNKNOWN`.

## State and observations

Bytes range over `B={0,...,255}`.  A configuration contains a program counter,
fixed-capacity objects, scalar registers, a partial length cache, a representation
marker, and an emitted integer sequence.  Each object cell has a byte payload and
an initialized bit.  Initial cells are literals, uninitialized cells, or references
to declared input bytes; repeated references denote one input value.  Only input
bytes, not uninitialized payloads, are quantified.

A cache is valid when every materialized `(object,offset)` entry equals the logical
length obtained by the scan rules below.  Correct writes invalidate every cache
entry for their base object.  A valid state may omit any cache entry.

A command either produces a successor or a terminal outcome:

* `accept(emits)` at normal end;
* `reject(emits)` when an `assume` condition is false; or
* `fault(tag,emits)` for `bounds`, `uninitialized`, `unterminated`, or `overlap`.

The first detected fault terminates and retains previous emissions.  Exact outcome
equality distinguishes tags and emitted sequences.  Both programs in a case start
from equal fresh objects, empty registers, empty cache, and empty emissions.

A **full-allocation string view** retains every cell, initialized bit, capacity,
and byte order, including initialized cells after the first NUL.  It is not the
prefix ending at NUL.  A `switch` changes only the representation marker.  The
universal theorem relates any two valid states with a common static interface;
the experimental cases ordinarily compare two programs from one common input
state.

## Access order and memory operations

A span `(o,n)` is in capacity `C` exactly when `0<=o`, `0<=n`, and `o+n<=C`.
A byte read checks its one-cell span before initialization.  A write checks the
entire destination span, writes supplied bytes, and invalidates all length-cache
entries for that base object.  Distinct base objects never alias; offsets within
one object may overlap.  Objects never allocate, free, resize, or share storage.

A terminator scan first validates the starting cell.  It reads in increasing
index order until the first zero.  Reading an uninitialized cell faults
immediately; reaching capacity without zero faults `unterminated`.  This order is
part of the semantics.

* `strlen(b,o)` returns `terminator(b,o)-o`.  `strlen_cached` returns the same
  logical value while using the valid cache.
* `strchr(b,o,c)` evaluates `c`, validates the complete terminated suffix by a
  scan, then returns the first relative occurrence including the terminator, or
  `-1`.  The whole-suffix precheck is a deliberate model choice.
* `strcmp` validates both terminated suffixes in operand order and returns only
  normalized unsigned sign `-1`, `0`, or `1`.
* `store` evaluates its source byte before validating/writing the destination.
* `memmove` checks both spans, reads a full source snapshot, then writes the
  snapshot.  A zero-length move reads no cell.
* `strcpy` scans the source including its NUL, checks the destination, rejects
  overlap on one base object, and copies the complete source.
* `strcat` scans source, then destination, writes at the destination NUL, and
  conservatively rejects overlap between the complete destination prefix plus
  appended region and the source span.
* `switch` preserves the complete allocation and changes only the view marker.

## Byte/scalar boundary

A stored byte is a literal or a previously read byte.  Input origins may be copied
but never arithmetically changed.  Byte questions are unsigned three-way
comparisons or fixed unary tests `(byte & mask)==equal`.  Search characters obey
the same byte-expression restriction.

Scalar expressions use constants or prior registers.  Widths 1--64 support add,
subtract, and, or, xor, and logical shifts.  Operands and results are reduced
modulo `2^width`; shifting by at least the width yields zero.  This totalized
bitvector rule is not ISO C undefined overshift.  Scalar comparisons compare the
stored integers without signed reinterpretation.  Lengths, search results,
normalized comparison signs, and byte-test Booleans are scalar values.  Scalars
may supply later offsets and sizes.  There is no scalar-to-byte cast.

## Intentional alternatives

The case language contains deliberately faulty candidate operations used as
negative controls, not alleged external defects:

* omit NUL from search;
* compare bytes as signed;
* omit the copy terminator;
* copy overlapping memory forward;
* retain a stale length cache;
* zero initialized tail after the first NUL; and
* treat capacity as the length of an unterminated object.

Their remaining checks follow the delivered interpreters.  `erase_tail` preserves
uninitialized status.  `copy_no_zero` still checks the full correct destination
span.  `move_forward` prechecks source initialization, then re-reads sequentially
during writes.

## Three properties compared

For program `P` and input assignment `rho`, let `O_P(rho)` be the exact outcome and
`A_P={rho | O_P(rho) is accept}`.

1. **Outcome equivalence:** `O_P(rho)=O_Q(rho)` for every input.
2. **Acceptance-set equality:** `A_P=A_Q`.
3. **SAT-status equality:** `A_P` and `A_Q` are either both empty or both nonempty.

Each implication goes downward, but the converses do not hold.  Certificates
report all three separately.  A disagreement witness is lexicographically least
in declared variable order over `0,...,255`; it is not a shortest program, minimum
heap, or minimum edit.

## Universal and continuation-specific relations

The universal switch theorem fixes a static interface and quantifies over every
well-typed continuation.  Its exact relation keeps capacities, initialized bits,
initialized bytes, scalar registers, and previous emissions; it quotients valid
cache representation, uninitialized payload, and the view marker.  See
`full_abstraction.md`.

For one fixed pair of continuations, the branch certificate may prove equality on
a coarser partition of the initial byte domain.  That relation is justified only
by complete coverage of the selected continuation and must not be reused as a
universal switch contract.
