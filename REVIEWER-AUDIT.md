# Reviewer-risk audit

This audit records repaired internal issues; it is not independent peer review.

## Closed issues

1. **Dependency mismatch.** `main.tex` and `reviewer-hardening.tex` now belong to the
   transitive build closure, and the PDF build checks for text unique to that input.
2. **Capacity/interface ambiguity.** Object names and persistent-register names
   form the interface; capacity is immutable state data bounded by `B`.
3. **Observation ambiguity.** Terminal observations contain status/fault plus
   emissions only.  Final heap and scalar stores are not returned directly.
4. **Temporary-register gap.** Fresh locals use a disjoint namespace, cannot shadow
   persistent registers, and are erased at termination.
5. **False finite basis.** The fixed basis uses eight predetermined bit probes per
   object/index, not state-dependent literals or only 0/1 equality tests.
6. **2/3 counterexample.** A retained executable control demonstrates the failure
   of the 0/1-only interpretation and success of the low-bit probe.
7. **Abstract-audit cardinality.** The record now says 1,296 base pairs plus three
   separately named controls, not 1,299 pairs from the 36-state universe.
8. **Mutation arithmetic.** All 18 actual names appear exactly once in groups
   7/4/3/4.
9. **Replay isolation.** Same-process in-memory checking, same-process file replay,
   and the one C135 independent CLI replay are described separately.
10. **Reproduction destruction risk.** New campaigns write only to an external,
    nonexistent directory; retained inputs are hashed before and after and never
    replaced.
11. **Accounting scope.** 99,999 is a frozen historical subset, C135 adds five
    post-freeze obligations, and no exact all-time total is fabricated.  Concrete
    assignments, pair/context checks, and single-side executions are separated.
12. **B.14 conflation.** Same-command relation preservation is separated from
    reference-versus-alternative equivalence; stale cache is treated as a validity
    failure.
13. **C167 metadata.** The schema's provisional default is disclosed, while the
    operational result remains `unknown_resource_exhaustion` and outside the 166
    completed verdicts.

## Remaining bounded risks

The Python replay kernel and its correspondence to the paper remain trusted.  The
case set is synthetic and cannot support claims about real-program utility or
performance.  A journal reviewer may request mechanization or integration, but
those would be new research beyond this paper's declared scope.
