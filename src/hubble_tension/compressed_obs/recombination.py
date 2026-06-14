from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from hubble_tension.schemas.replication import CompressedObservableReport, ReferenceComparison


@dataclass(frozen=True)
class ReferenceObservable:
    value: float
    tolerance: float
    source: str


# Phase 11 uses a deterministic HyRec-2-compatible fixture row until the real
# solver build imports version-pinned HyRec-2 output files. These values are
# intentionally treated as compressed regression checks, not full recombination
# validation.
HYREC2_RECOMBINATION_REFERENCE: Final[Mapping[str, ReferenceObservable]] = {
    "z_rec": ReferenceObservable(
        value=1089.92,
        tolerance=1.0,
        source="HyRec-2-compatible Lambda-CDM fixture aligned to Planck 2018 z_*",
    ),
    "tau_rec": ReferenceObservable(
        value=280.0,
        tolerance=8.0,
        source="HyRec-2-compatible visibility-peak conformal-time fixture",
    ),
    "sigma_rec": ReferenceObservable(
        value=19.0,
        tolerance=3.0,
        source="HyRec-2-compatible visibility-width fixture",
    ),
}


def compare_recombination_history(
    observables: Mapping[str, float],
    *,
    reference: Mapping[str, ReferenceObservable] = HYREC2_RECOMBINATION_REFERENCE,
) -> CompressedObservableReport:
    """Compare recombination compressed observables against reference output."""

    comparisons: list[ReferenceComparison] = []
    missing: list[str] = []
    failed: list[str] = []
    for observable, expected in reference.items():
        if observable not in observables:
            missing.append(observable)
            continue
        value = float(observables[observable])
        deviation = abs(value - expected.value)
        passed = deviation <= expected.tolerance
        if not passed:
            failed.append(observable)
        comparisons.append(
            ReferenceComparison(
                observable=observable,
                value=value,
                reference=expected.value,
                tolerance=expected.tolerance,
                deviation=deviation,
                passed=passed,
                source=expected.source,
            )
        )

    if missing:
        status = "missing_observable"
    elif failed:
        status = "failed_reference_table"
    else:
        status = "passed_reference_table"

    return CompressedObservableReport(
        observable_set="recombination_history",
        status=status,
        comparisons=tuple(comparisons),
        failed_observables=tuple(failed),
        missing_observables=tuple(missing),
        approximation_limit="hyrec2_fixture_not_full_recombination_solver",
    )
