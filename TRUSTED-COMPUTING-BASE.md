# Trusted computing base

The certificate producer, case generator, stored summaries, and manuscript tables are **not trusted** for certificate acceptance.

Acceptance relies on: (1) the Python runtime and standard integer/JSON string semantics; (2) `src/strict_json.py`; (3) the replay kernel identified in `SPEC-CODE-MAP.csv`; and (4) the human-reviewed correspondence between that kernel and the paper definitions. Resource exhaustion, malformed input, unknown fields, and failed obligations must reject or return `UNKNOWN`; they must never be converted to equivalence.

The project does not claim a proof-assistant refinement theorem for the Python implementation, an ISO C or LLVM front-end theorem, or correctness of an external SMT encoding. Those are excluded claims, not hidden premises.
