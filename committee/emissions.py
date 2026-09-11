"""Every code every lens can emit, read out of the source with ``ast``.

Derived, not declared. The alternative was an ``EMITS`` constant in each of the
eight ``checks.py`` files, which would restate what the code already says and
so could disagree with it -- the thing this package exists to stop. So the
table is parsed, and the parser's own blindness is made detectable:
:func:`unparsed_sites` returns every construction site it did NOT understand,
and a test asserts that set is empty. A silent parse miss would make this whole
layer confidently wrong, which is worse than not having it.

Why ``ast`` and not a regex: two sites in ``detection/checks.py`` build the code
with a conditional --

    return CheckResult(
        "sampling" if ok else "sampling.undersampled",
        SOFT, margin, "ok" if ok else "fail", ...

-- and the first regex written for this missed both, which is how
``sampling.undersampled`` came to be absent from a hand-written audit. A
conditional emits **both** codes; nothing but a parse will say so.
"""

from __future__ import annotations

import ast
import functools
import pathlib
from dataclasses import dataclass

#: The eight lenses in committee order, which is what `L<lens>.<n>` counts from.
LENSES: tuple[str, ...] = (
    "optics",
    "detection",
    "compute",
    "sample",
    "photo",
    "validity",
    "trapping",
    "stability",
)

_REPO = pathlib.Path(__file__).resolve().parent.parent

#: Severity that `_ok` stamps on, per lens. It is NOT uniform, and the
#: difference is load-bearing: every `gate.py` drops `severity == "ok"` from
#: `findings`, so a lens whose `_ok` says "ok" hides its passing computations
#: in `metrics`, and one whose `_ok` says "info" shows them. Lenses 5, 7 and 8
#: were changed to "info" during the 2026-09 review after that defect appeared
#: five times. See `invisible_computations`.
_OK_SEVERITY: dict[str, str] = {
    "optics": "ok",
    "detection": "ok",
    "compute": "ok",
    "sample": "ok",
    "photo": "info",
    "validity": "ok",
    "trapping": "info",
    "stability": "info",
}

_KINDS = {"HARD": "hard", "BIAS": "bias", "SOFT": "soft", "INFO": "info"}
_CONSTRUCTORS = {"CheckResult", "_ok"}


@dataclass(frozen=True)
class EmissionSite:
    """One code one check can put into a ``Verdict``.

    A check with a conditional code or severity yields several of these, which
    is the point: a branch that only fires on failure is still an emission.
    """

    lens: str
    #: `L<lens>.<n>`, or None for a helper that is not a registered check.
    address: str | None
    #: The `Check.code` of the enclosing check, e.g. `wall_drag`.
    check: str | None
    #: The code that reaches the `Finding`, e.g. `geometry.wall_drag.trapped`.
    emitted_code: str
    #: hard | bias | soft | info -- of the RESULT, which is what consumers
    #: filter on, and not necessarily the owning `Check`'s registration.
    kind: str
    severity: str  # ok | info | warn | fail
    line: int

    @property
    def visible(self) -> bool:
        """Does this reach ``Verdict.findings``?

        Every ``gate.py`` drops ``severity == "ok"``, so a site that is not
        visible exists only in ``metrics`` -- which no CLI prints.
        """
        return self.severity != "ok"

    @property
    def reaches_bias_ledger(self) -> bool:
        """Would ``validity.setup.bias_findings`` collect this?

        BIAS by the RESULT's kind, at a severity some gate will put in
        ``findings``. `validity` itself is excluded: its ledger reads
        ``upstream`` only, so it cannot feed itself.
        """
        return (
            self.kind == "bias"
            and self.visible
            and self.lens != "validity"
        )


#: Name -> the IfExp it was bound to, for the current function. Filled by
#: `_string_bindings` and read by `_resolve_ifexp`, so that a severity assigned
#: to a local can still be recognised as a conditional and paired with a
#: conditional code.
_ifexp_bindings: dict[str, ast.IfExp] = {}


def _string_bindings(fn: ast.FunctionDef) -> dict[str, list[str]]:
    """Local names bound to a string, or to a conditional between strings.

    `optics/checks.py` assigns the severity first and passes the name:

        severity = "warn" if ratio < 0.5 else "ok"
        return CheckResult("excitation.coupling", HARD, margin, severity, ...)

    Resolving one level of that is the difference between seeing those two
    sites and filing them as unparsed. A name bound more than once, or bound
    to anything else, is dropped rather than resolved to the last value --
    guessing there is how a parser becomes confidently wrong.
    """
    seen: dict[str, list[str] | None] = {}
    _ifexp_bindings.clear()
    for node in ast.walk(fn):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        value = _literal_or_branches(node.value)
        seen[target.id] = None if target.id in seen else value
        if value and isinstance(node.value, ast.IfExp):
            _ifexp_bindings[target.id] = node.value
    return {k: v for k, v in seen.items() if v}


def _literal_or_branches(
    node: ast.AST, bindings: dict[str, list[str]] | None = None
) -> list[str] | None:
    """Every string a code/severity expression can evaluate to, or None.

    Handles a constant, a one-level conditional, and a local name bound to
    either -- which is all the source uses. Anything else returns None and
    lands in :func:`unparsed_sites` rather than being guessed at.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.IfExp):
        a = _literal_or_branches(node.body, bindings)
        b = _literal_or_branches(node.orelse, bindings)
        if a is None or b is None:
            return None
        return a + b
    if bindings is not None and isinstance(node, ast.Name):
        return bindings.get(node.id)
    return None


def _resolve_ifexp(
    node: ast.AST, bindings: dict[str, list[str]]
) -> ast.IfExp | None:
    """The conditional behind an expression, following one local binding."""
    if isinstance(node, ast.IfExp):
        return node
    if isinstance(node, ast.Name):
        return _ifexp_bindings.get(node.id)
    return None


def _pair(
    code_node: ast.AST,
    codes: list[str],
    severity_node: ast.AST | None,
    severities: list[str],
    bindings: dict[str, list[str]],
) -> list[tuple[str, str]]:
    """Pair codes with severities, respecting a shared condition.

    ⚠ THE CROSS PRODUCT IS WRONG HERE AND THE ERROR IS NOT HARMLESS.
    `detection/checks.py` writes

        CheckResult("sampling" if ok else "sampling.undersampled",
                    SOFT, margin, "ok" if ok else "fail", ...)

    and the two conditionals are the SAME condition, so only two of the four
    combinations exist. Taking the product invents `("sampling", "fail")` --
    which is a BIAS-kind, findings-visible code that cannot actually occur, and
    it duly showed up in the first run of this layer as an unregistered ledger
    code somebody would have been sent to register. Same-condition
    conditionals are zipped; anything else falls back to the product, which
    over-reports rather than under-reports.
    """
    c_if = _resolve_ifexp(code_node, bindings)
    s_if = _resolve_ifexp(severity_node, bindings) if severity_node else None
    if (
        c_if is not None
        and s_if is not None
        and len(codes) == len(severities)
        and ast.dump(c_if.test) == ast.dump(s_if.test)
    ):
        return list(zip(codes, severities))
    return [(c, s) for c in codes for s in severities]


def _kind_of(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name) and node.id in _KINDS:
        return _KINDS[node.id]
    if isinstance(node, ast.Constant) and node.value in _KINDS.values():
        return str(node.value)
    return None


def _addresses(lens: str) -> dict[str, tuple[str, str]]:
    """fn name -> (address, check code), from the docstring and the registry."""
    import importlib
    import re

    src = (_REPO / lens / "checks.py").read_text()
    addr = {
        m.group(1): m.group(2)
        for m in re.finditer(
            r'def (check_\w+)\([^)]*\)[^:]*:\s*(?:r?"""|\'\'\')(L\d+\.\d+)', src
        )
    }
    codes = {c.run.__name__: c.code for c in importlib.import_module(lens + ".checks").CHECKS}
    return {fn: (addr.get(fn), codes.get(fn)) for fn in set(addr) | set(codes)}


def _walk(lens: str) -> tuple[list[EmissionSite], list[tuple[int, str]]]:
    src = (_REPO / lens / "checks.py").read_text()
    tree = ast.parse(src)
    meta = _addresses(lens)
    ok_sev = _OK_SEVERITY[lens]

    sites: list[EmissionSite] = []
    unparsed: list[tuple[int, str]] = []

    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef):
            continue
        # The `_ok` helper builds a CheckResult from its own arguments. It is
        # the mechanism, not an emission, so its body is skipped -- every call
        # to it is counted at the call site instead.
        if fn.name == "_ok":
            continue
        address, check = meta.get(fn.name, (None, None))
        bindings = _string_bindings(fn)
        for node in ast.walk(fn):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None)
            if name not in _CONSTRUCTORS:
                continue
            args = node.args
            if len(args) < 2:
                unparsed.append((node.lineno, "fewer than two positional args"))
                continue
            codes = _literal_or_branches(args[0], bindings)
            kind = _kind_of(args[1])
            if codes is None or kind is None:
                unparsed.append((node.lineno, "non-literal code or kind"))
                continue
            if name == "_ok":
                severities, severity_node = [ok_sev], None
            elif len(args) >= 4:
                severity_node = args[3]
                severities = _literal_or_branches(severity_node, bindings) or []
                if not severities:
                    unparsed.append((node.lineno, "non-literal severity"))
                    continue
            else:
                unparsed.append((node.lineno, "CheckResult with no severity"))
                continue
            for code, sev in _pair(args[0], codes, severity_node, severities,
                                   bindings):
                sites.append(
                    EmissionSite(lens, address, check, code, kind, sev, node.lineno)
                )
    return sites, unparsed


@functools.lru_cache(maxsize=None)
def collect(lens: str) -> tuple[EmissionSite, ...]:
    """Every emission site in one lens, deduplicated, in source order."""
    sites, _ = _walk(lens)
    seen: dict[tuple, EmissionSite] = {}
    for s in sites:
        seen.setdefault((s.emitted_code, s.kind, s.severity), s)
    return tuple(seen.values())


def collect_all() -> tuple[EmissionSite, ...]:
    return tuple(s for lens in LENSES for s in collect(lens))


@functools.lru_cache(maxsize=None)
def unparsed_sites(lens: str) -> tuple[tuple[int, str], ...]:
    """Construction sites the parser did not understand, as (line, why).

    **This must stay empty.** A miss here is not a gap in a report, it is this
    layer claiming a code cannot be emitted when it can.
    """
    return tuple(_walk(lens)[1])


def ledger_reachable_codes() -> frozenset[str]:
    """The codes that can reach `validity`'s bias ledger."""
    return frozenset(s.emitted_code for s in collect_all() if s.reaches_bias_ledger)


def invisible_computations() -> tuple[EmissionSite, ...]:
    """Sites that compute a number and put it where nothing prints it.

    ``severity == "ok"`` is dropped from ``findings`` by every ``gate.py``, so
    these live only in ``metrics``. That is right for a pass whose basis a
    reader can reconstruct and wrong for a pass that made a choice -- the
    distinction drawn on 2026-09-11 after the defect appeared five times
    (kb/decisions/2026-09-11-a-pass-that-decides-must-be-visible.md). This
    function does not judge which is which; it lists the candidates.
    """
    return tuple(s for s in collect_all() if not s.visible)


@dataclass(frozen=True)
class Reconciliation:
    """The two-way diff between what is emitted and what lens 6 registers."""

    #: Registered in CORRECTIONS/UNCORRECTABLE, emitted by nobody. A
    #: declaration naming one of these matches nothing and nobody is told.
    registered_without_emitter: tuple[str, ...]
    #: Emitted into the ledger, in neither registry. Accepted, but it pins
    #: `evidence: assumed` because nobody has audited whether a correction
    #: exists.
    emitted_without_registry: tuple[str, ...]
    #: Both -- the only codes whose declaration this repository can check.
    agreed: tuple[str, ...]

    @property
    def clean(self) -> bool:
        return not (self.registered_without_emitter or self.emitted_without_registry)

    def summary(self) -> str:
        lines = [
            f"agreed                     {len(self.agreed):3}  "
            + ", ".join(self.agreed),
            f"registered, not emitted    {len(self.registered_without_emitter):3}  "
            + ", ".join(self.registered_without_emitter),
            f"emitted, not registered    {len(self.emitted_without_registry):3}  "
            + ", ".join(self.emitted_without_registry),
        ]
        return "\n".join(lines)


def reconcile_bias_registry() -> Reconciliation:
    """Diff the emitted bias codes against `validity.setup`'s two registries."""
    from validity.setup import CORRECTIONS, UNCORRECTABLE

    registered = frozenset(CORRECTIONS) | frozenset(UNCORRECTABLE)
    emitted = ledger_reachable_codes()
    return Reconciliation(
        registered_without_emitter=tuple(sorted(registered - emitted)),
        emitted_without_registry=tuple(sorted(emitted - registered)),
        agreed=tuple(sorted(registered & emitted)),
    )
