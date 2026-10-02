# Result inventory and scopes

This directory contains immutable historical result files plus explicit repair-era
reconciliation records.  Historical files are not rewritten to erase
contradictions; later records state their exact scope.

## Historical evidence

- `final_reproduction.json`, `branch_cases.csv`, and `certificates/branch/` retain
  the original C001--C166 completion batch.
- `final_continuation_audit.json` retains the later C001--C165 file replay,
  320-instance regional cross-check, direct concrete checks, repeated abstraction
  work, and repeated mutation suite.
- `final_clean_extract_audit.json` retains the five-case clean-extract replay.
- `resource_accounting.csv` is the original phase ledger and contains a legacy
  mixed concrete column.
- `documented_replay_smoke.json` records the successful C135 CLI smoke.

## Reconciliation records

- `full_abstraction_reconciliation.json`: 1,296 base pairs plus three directed
  controls; corrected 18-test basis; 1,262 short-witness comparisons; byte-2/3
  control; complete eight-bit signature audit.
- `mutation_grouping.json`: exact mutually exclusive 7/4/3/4 grouping of the 18
  real mutation names.
- `C167_status_reconciliation.json`: schema default versus cap-induced
  `unknown_resource_exhaustion` and exclusion from the 166 completed results.
- `accounting_scope_reconciliation.json`: separates obligations, concrete input
  assignments, pair/context comparisons, and single-side program executions.
- `documented_replay_smoke_accounting.json`: C135 uses four region calls plus one
  top-level check and is outside the frozen 99,999 subledger.
- `process_isolation_reconciliation.json`: original in-memory checking, later
  same-process file rereads, isolated-campaign rereads, and the single C135 CLI
  process are recorded separately.
- `isolated_campaign_acceptance.json`: post-repair read-only-input campaign,
  result closure, environment, digest scope, and actual process modes.

The frozen 99,999 count ends at the clean-extract replay.  It is not an all-time
total.  C135 adds five same-rule post-freeze obligations; other later QA was not
uniformly instrumented.  The old 650,557 display is a superseded mixed field, not
a homogeneous count.  No replacement historical grand total is fabricated.

The isolated campaign digest covers every artifact file except bytecode/cache and
the self-referential `results/isolated_campaign_acceptance.json` record.  That same
exclusion is used for the campaign's static and retained-evidence snapshots, so the
before/after integrity comparison has a stable, stated scope.
