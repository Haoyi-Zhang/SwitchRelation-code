# Proof-carrying hybrid string

This standalone artifact accompanies *Exact Switching Relations and Replayable
Certificates for Bounded String Views*. It provides bounded deterministic
semantics, proofs, a certificate producer and a separately structured replayer,
167 owned synthetic cases and 166 retained certificates. It is not a C/LLVM
frontend, general SMT proof checker or real-system performance study.

## Setup and quick checks

Use CPython 3.11 or newer. Semantic modules use only the standard library; no
package installation, network, external solver or GPU is needed. From this root:

```sh
python -B inspect_packet.py
python -B -O inspect_packet.py
python -B -m unittest discover -s tests -p 'test_*.py' -v
python -B src/branch_replay.py cases/C135.json certificates/branch/C135.json
```

Packet inspection is structural, not semantic reproduction. Unit tests include
focused semantic regressions but are not the full campaign. The documented C135
CLI replay uses four regional calls plus one top-level check. The legacy
`src/structural_audit.py` writes under `results/`; use a disposable copy for it.

## Fresh reproduction

Treat retained `results/` and `certificates/` as read-only evidence. Fresh
campaign directories must not exist and must be outside the artifact.

The portable finite route is:

```sh
python -B src/scientific_checks.py --output-dir ../scientific-run
```

It regenerates 167 schemas, serializes/re-reads/replays 166 new certificates,
checks the finite basis and 384 fresh-seed regions, retains 18 owned mutation
controls, and requires C167 to hit its node cap. It has a 120-second wall guard;
POSIX additionally limits address space to 1 GiB and CPU to 100/110 seconds.
Windows skips the existing POSIX-only primitive oracle and has no internal hard
memory limit. Partial external outputs remain on failure. Every certificate is
replayed in the campaign process, not a new process per certificate.

The historical POSIX reproduction driver separately supports:

```sh
python -B reproduce.py --output-dir ../campaign --region-instances 384
```

Its tested path uses one worker, a 2500-MiB address-space limit, 110/115-second
CPU limits and a 118-second wall alarm. It snapshots static inputs and retained
evidence and checks an aggregate input-tree digest before/after execution.
Only C135 additionally receives an independent CLI-process replay. It does not
replace checked-in results. Two passing campaigns can be merged without changing
either input:

```sh
python -B src/merge_campaigns.py ../campaign-a ../campaign-b --output-dir ../merged
```

The scientific workflow runs portable checks and direct-path checks on Ubuntu,
with raw-output retention on success or failure. The optional
`python -B tests/regression_unary_bitmap.py -v` checks the producer's exact bitmap
cache, retained cases, refusals and mutation kinds; it writes no retained results
and is not a historical-campaign rerun. No cache speedup is measured or claimed.

## Replay contract and retained evidence

For a fixed pair of bounded continuations, the certificate binds the complete
statement, partitions the input cube, and stores outcomes and regional minima.
The replayer traverses the complete certificate tree; it does not first strip
top-level `switch` commands and accept by syntactic comparison. In its list
interpreter, `switch` itself is `pass` with no data effect because the view marker
is quotiented out. It still reconstructs every region and re-executes both
programs, checking their outcomes at every leaf.

The 150 equivalent cases comprise 31 identical program pairs, 105 pairs differing
only by `switch` commands, and 14 pairs with other program rewrites. The first
two groups exercise replay of unchanged computations and view changes; the 14
remaining pairs exercise outcome-preserving rewrites beyond switch insertion.
The 166 certificates and 6,281 leaves measure replay work, not distinct rewrites.
The other 16 completed cases are different. C167's provisional schema expectation
is not a verdict: it has no certificate and remains
`unknown_resource_exhaustion` at the 6,000-node cap.

Original in-memory checks, later same-process file replays and the one C135 CLI
smoke remain distinct in `results/process_isolation_reconciliation.json`.
The isolated acceptance record is `results/isolated_campaign_acceptance.json`;
the later Windows run is in `results/portable-campaign/`. Their recorded
measurements describe their own runs and do not replace historical evidence.

The 99,999/100,000 obligation ledger is a frozen historical subset, not an
all-time total. The later C135 smoke contributes five separate obligations;
the recorded same-rule lower bound after that smoke is 100,004. Other work was
not uniformly instrumented. Assignments, pair/test comparisons and single-side
executions are separate overlapping units; use
`results/accounting_scope_reconciliation.json` rather than summing them.

## Inputs, implementation and conditions

- `cases/`, `certificates/branch/`: case statements and retained C001--C166 trees.
- `src/branch_producer.py`, `order_domain.py`: producer and exact region solver.
- `src/branch_replay.py`, `strict_json.py`: interpreter, regional checker and
  strict bounded JSON loader.
- `src/contextual.py`, `check_full_abstraction.py`: allocation relation,
  distinguishing continuations and fixed-basis checks.
- `src/check_regions.py`, `primitive_oracle.py`, `check_mutations.py`:
  finite oracles and the 18 owned negative controls.
- `proofs/`, `ASSUMPTION-DEPENDENCY.md`, `TRUSTED-COMPUTING-BASE.md`:
  normative semantics, assumptions and trust boundary.
- `SPEC-CODE-MAP.csv`, claim/evidence ledgers and `external_resources.csv`:
  executable correspondence, evidence and provenance consumers.

The full-allocation relation preserves capacities, initialization, initialized
bytes, persistent scalars and prior output while quotienting valid cache
materialization, uninitialized payload and view. Continuation locals start empty;
carried live scalars belong to the persistent interface. See
`proofs/full_abstraction.md` and `proofs/semantics.md` for the exact language,
observation and fixed-basis contracts. Resource exhaustion is `UNKNOWN`, not
evidence of equivalence or difference.

Python, the loader, replay kernel and their correspondence to the written model
remain trusted. No proof-assistant refinement, native C/LLVM correspondence,
real-software coverage, solver-performance dominance or independent human-review
claim follows from these finite synthetic checks.

## License

Project code, inputs and original documentation use the accompanying MIT
`LICENSE`. External-resource and source records retain their existing terms.
