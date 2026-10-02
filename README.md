# Proof-carrying hybrid string

This standalone repository accompanies *Exact Switching Relations and Replayable
Certificates for Bounded String Views*.  It contains a bounded deterministic
semantics, paper proofs, a certificate producer, a separately structured replayer,
167 owned synthetic cases, 166 retained certificates, finite audits, mutation
tests, and reconciled evidence records.  Its scope is deliberately limited: it is
not a C/LLVM frontend, a general SMT proof checker, or a real-system performance
study.

## Established results and contracts

For valid states over a fixed name interface and a global capacity bound `B`, the
full-allocation relation preserves each state's object capacities, initialization
bits, initialized bytes, persistent registers, and prior emissions while
quotienting valid cache materialization, hidden uninitialized payload, and the view
tag.  Capacity is state data, not a component that states must share merely by
interface typing.  `proofs/full_abstraction.md` proves that this relation is
exactly terminal observational equivalence for all well-typed continuations in the
declared language.

Persistent registers and continuation-local temporaries are disjoint.  Result
binders are fresh locals, locals are erased at termination, and terminal
observation contains only accept/reject/fault status plus emissions.  There is no
direct byte-output command and no final register-store observation.

Two distinct separation results are implemented:

* a state-dependent distinguishing continuation of at most two commands; and
* a fixed state-independent basis with three syntactic templates and exactly
  `1 + |R| + 8*B*|O|` instantiated tests.

The fixed byte probe observes one predetermined bit through the declared
`mask_eq` operation.  Equality tests only against 0 and 1 are not complete: the
retained one-cell byte-2/byte-3 control defeats both but is separated by the low
bit.  The audit also checks all 65,536 ordered byte pairs and confirms 256 unique
eight-bit signatures.

For a fixed pair of bounded continuations, a certificate binds the complete case,
partitions the finite input cube by exact byte questions, stores terminal outcomes
and regional minima, and closes infeasible answers.  The replayer reconstructs the
regions, re-executes both programs, and recomputes outcome equivalence, acceptance
sets, satisfiability, and the least disagreement.  The uncapped mathematical
procedure terminates on the finite domain; configured limit exhaustion is
`UNKNOWN`.

## Retained evidence and process modes

The original completion batch generated C001--C166, checked each new certificate
in memory in the same process, and then serialized it.  It retained 150 equivalent
and 16 different determinations, 9,986 nodes, 6,281 leaves, 1,281 closed answers,
and 11,267 producer plus 11,267 replayer regional calls.  A later audit loaded
C001--C165 from files and replayed them in one audit process; a clean-extract audit
loaded five selected certificates in one process.  These are not described as 166
fresh-process replays.

The repaired isolated campaign serializes and re-reads all 166 newly generated
certificates before replay in the campaign process.  C135 additionally receives an
independent CLI-process replay.  The acceptance record is
`results/isolated_campaign_acceptance.json`.

C167's schema really contains the generator default `expected="equivalent"`, but
that provisional field is not a validated verdict.  At the 6,000-node cap the
producer returned `unknown_resource_exhaustion`; no certificate exists, and C167
is excluded from the 166 completed determinations.

The finite abstraction reconciliation reports:

| Unit | Value |
|---|---:|
| Fixed-capacity base states | 36 |
| Base ordered pairs | 1,296 |
| Separate directed controls | 3 |
| Total base-plus-control checks | 1,299 |
| Related / unrelated checks | 37 / 1,262 |
| Fixed tests per pair (`B=2`, one object, one register) | 18 |
| Fixed-basis pair/test comparisons | 23,382 |
| State-dependent witness comparisons | 1,262 |
| Corrected single-side program executions | 49,294 |
| Ordered byte-signature checks | 65,536 |

The three controls cover unequal capacity, unequal initialization, and a related
pair differing only in valid cache presence, view, and hidden uninitialized
payload.  The historical `finite_basis_executions=222` field meant 37 related
pairs times a former six-test 0/1 basis at the pair-comparison level.  It omitted
the 1,262 unrelated-pair witness checks and is not the corrected fixed-basis work
count.

The 18 retained mutations are partitioned exactly once as 7/4/3/4; see
`results/mutation_grouping.json` and `proofs/arguments.md`.  All were rejected.

## Accounting scopes

`99,999 / 100,000` is a frozen historical obligation subledger ending with the
five-case clean-extract replay.  It is not an all-time count.  The later documented
C135 CLI replay used four region calls plus one top-level check, so it contributes
five separate post-freeze obligations and yields a same-rule known lower bound of
100,004.  Other post-freeze QA was not uniformly instrumented; no exact all-time
total is claimed.

Concrete work is kept in homogeneous units.  Named input-assignment enumerations
are 65,536 primitive-oracle assignments, 11,292 original regional assignments,
9,872 continuation regional assignments, and 480,697 continuation direct-case
assignments, for a named subtotal of 567,397.  The inherited 92,810 field remains
visible but is not added because its historical record does not fully disaggregate
units.  The old 650,557 display is retained only as a superseded mixed field.

Single-side program executions are separately derivable as 2,968 for each original
and repeated historical full-abstraction run, 49,294 for the repaired basis audit,
and 1,049,174 for the continuation direct audit.  Runs overlap, so no grand total
across these rows is claimed.

## Safe isolated reproduction

The retained `results/` and `certificates/` trees are read-only evidence.  A new
campaign must write to a nonexistent directory outside this repository:

```sh
python reproduce.py --output-dir ../campaign --region-instances 384
```

The driver refuses output inside the artifact root, records an aggregate scientific
input digest before and after execution, copies the exact static inputs and retained
comparison evidence used, and writes all new certificates/results below the
external campaign directory.  It does not replace `results/`.

Two passing isolated campaigns can be merged without modifying either input:

```sh
python src/merge_campaigns.py ../campaign-a ../campaign-b \
  --output-dir ../merged
```

Only like-for-like units are summed.  Historical frozen-ledger values are not
imported into a new campaign.

The accepted disposable-copy run used CPython 3.13.5 on Linux x86-64, one worker,
a 2.5-GiB address-space limit, 110/115-second CPU limits, and a 118-second wall
alarm.  The semantic code uses the Python standard library.  The tested
prerequisite is CPython 3.11 or newer on a POSIX-like system with the resource
interfaces used by the driver.

Package-only checks, which do not constitute a new scientific run, are:

```sh
python inspect_packet.py
python -O inspect_packet.py
python -m unittest discover -s tests -p 'test_*.py' -v
python src/structural_audit.py
```

A single retained certificate can be checked with:

```sh
python src/branch_replay.py cases/C135.json certificates/branch/C135.json
```

That successful command performs four regional checks and one top-level check and
must be accounted as five obligations in a new campaign.

## Repository map

* `src/contextual.py`, `src/check_full_abstraction.py`: relation, witnesses, fixed
  basis, and finite audits.
* `src/order_domain.py`, `src/branch_producer.py`: producer region solver and tree
  construction.
* `src/branch_replay.py`: separately structured interpreter, region checker, and
  fail-closed certificate replay.
* `src/strict_json.py`: strict, size-bounded JSON loading before allocation.
* `src/check_regions.py`, `src/primitive_oracle.py`: finite direct oracles.
* `src/check_mutations.py`: the exact 18 mutation controls.
* `src/merge_campaigns.py`: unit-aware merge for isolated campaign summaries.
* `cases/`: C001--C167 schemas.
* `certificates/branch/`: retained C001--C166 certificates.
* `proofs/`: normative semantics and proof arguments.
* `results/`: immutable historical evidence and explicit reconciliation records.

## Trust boundary and non-claims

The producer, stored summaries, and manuscript tables are not trusted for
certificate acceptance.  Acceptance relies on the Python runtime, strict loader,
replay kernel, and the human correspondence between code and paper definitions.
There is no proof-assistant refinement theorem for Python and no theorem connecting
this semantics to ISO C, LLVM, or a general SMT string/bit-vector encoding.

All cases are owned and synthetic.  No external executor, solver, application,
service, vulnerability, or real-system workload was run.  No solver-performance,
whole-program coverage, publication, acceptance, or independent-review claim is
made.
