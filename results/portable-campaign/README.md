# Portable finite checks

This directory retains actual Windows 11 / CPython 3.12.14 outputs from the
shared-loader campaign and the separate direct semantic check. `campaign.log`
contains the actual phase stream; the JSON files retain case materialization,
finite abstraction and region checks, certificate totals, mutation outcomes,
the resource-exhausted C167 case and measured runtime. The primitive oracle
requires POSIX resource interfaces and was not executed in this Windows run.

The campaign generated and checked 166 certificates in one process, with
150 equivalent and 16 different verdicts. Its exact case objects match the
retained corpus. Generated certificate objects also match the retained
`certificates/branch/` objects. They are not duplicated here. The direct
route consumed those newly checked certificates, exhaustively comparing
seven zero-origin, 52 one-origin and seven two-origin differing cases across
three concrete own-model implementations. Its 472,071 assignments and
6,281 leaf-minimum checks give 2,844,988 single-side executions. The leaf
checks use the direct interpreter; the complete assignment loops use all
three paths. Other multi-origin cases have no full-domain direct claim.

Raw records contain the actual external evidence-directory paths used during
execution. `src/scientific_checks.py --output-dir <new-directory>` regenerates
the full checked-certificate set. Then run:

```sh
python -B src/direct_checks.py --certificates <new-directory>/certificates --output-dir <new-direct-directory>
```

Both evidence destinations must be new and outside the source extraction.
Each command has a 120-second wall guard and keeps partial outputs on
failure. Windows applied no internal POSIX memory/CPU limit and did not
measure peak RSS. These are separately recorded checks, not rewrites of the
historical campaign or its frozen 99,999-obligation accounting.
