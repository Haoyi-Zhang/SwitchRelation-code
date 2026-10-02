# Assumption-to-claim dependency

| Assumption | Required by | Failure mode when changed |
|---|---|---|
| A global finite capacity bound `B`, while each object's immutable capacity remains state data | fixed finite basis; finite regional termination | an unbounded capacity family needs a different basis/termination argument; forcing capacity into the shared interface would erase a real separator |
| The static interface contains only object names and persistent-register names | exact/maximal relation; fixed basis | adding capacity values or local names to the interface changes the quantified state class |
| Terminal observation is exactly accept/reject/labeled-fault status plus the emitted sequence | full abstraction; basis completeness | exposing the final heap or either scalar store makes additional components observable |
| Persistent registers and continuation-local temporaries use disjoint typed namespaces; locals are erased at termination | fixed-interface theorem; constructive witnesses and bit probes | a fresh proof binder could shadow or silently extend the persistent interface |
| Fault tags and their first-occurrence order are observable | converse separators; exact leaf summaries | collapsing fault kinds/orders induces a coarser equivalence |
| Uninitialized payload cannot be read before the `uninitialized` fault | quotient over hidden physical payload | direct raw-memory observation would make ignored payload relevant |
| Every materialized cache entry is valid for its source allocation | cache representation quotient; same-command simulation | a stale cache may leave the valid-state domain and needs a separate validity argument |
| Primitive semantics are deterministic | exact functional observations; least witnesses | nondeterminism requires trace- or set-valued observations |
| Byte predicates include the declared fixed unary `mask_eq` operation | state-independent finite byte basis | equality only against 0/1 is not complete for 256 byte values |
| Resource exhaustion and malformed evidence fail closed | executable acceptance contract | a partial tree or parse failure could otherwise be promoted to a semantic verdict |
