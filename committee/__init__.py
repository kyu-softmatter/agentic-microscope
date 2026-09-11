"""The committee's own bookkeeping: what each lens can emit, and who listens.

**Not a lens.** The eight lenses judge a proposal; this package judges the
*wiring between them*. It exists because two failure modes in that wiring are
silent, and both bit repeatedly through the 2026-09 review:

1. **A lens emits a code nobody registered.** `validity`'s bias ledger accepts
   an unknown code -- refusing one would block work on gates its tables have
   not caught up with -- but an unaudited clearance pins the verdict's evidence
   to `assumed` forever. Seven codes were in that state.
2. **A registry names a code nobody emits.** Declaring it in
   `corrections_applied` then matches nothing: it neither clears a bias nor
   reads as a false claim, and nothing tells the declarer. Seven more.

Those two sets were kept as a hand-written snapshot in
`tests/test_gate_registry.py` and were wrong by two the first time they were
counted, because the obvious way to count them is wrong: `bias_findings`
filters on the **result's** kind, not on the owning `Check`'s registration, so
a BIAS-kind result emitted from an INFO-registered check does reach the ledger.

    from committee import collect_all, reconcile_bias_registry

    for site in collect_all():
        print(site.address, site.emitted_code, site.kind, site.severity)

    print(reconcile_bias_registry().summary())

KH asked for this on 2026-09-11 ("추후에 모든 방출 정보를 모으는 레이어를 하나
만들거야") rather than having the registries hand-reconciled, on the grounds
that a table edited to match today's emitters drifts again on the next gate
change -- which it had already done twice.
"""

from __future__ import annotations

from .emissions import (
    LENSES,
    EmissionSite,
    Reconciliation,
    collect,
    collect_all,
    invisible_computations,
    ledger_reachable_codes,
    reconcile_bias_registry,
    unparsed_sites,
)

__all__ = [
    "LENSES",
    "EmissionSite",
    "Reconciliation",
    "collect",
    "collect_all",
    "invisible_computations",
    "ledger_reachable_codes",
    "reconcile_bias_registry",
    "unparsed_sites",
]
