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


# Planck 2018 base-Lambda-CDM compressed CMB fixture values.
# theta_s_100 is the published 100*theta_* value; l_a and shift_parameter_r
# follow the Planck-2018 distance-prior convention used by many CMB-compression
# studies. Tolerances are scaffold regression tolerances, not publication errors.
PLANCK2018_CMB_REFERENCE: Final[Mapping[str, ReferenceObservable]] = {
    "theta_s_100": ReferenceObservable(
        value=1.04109,
        tolerance=0.001,
        source="Planck 2018 base-Lambda-CDM TT,TE,EE+lowE+lensing",
    ),
    "shift_parameter_r": ReferenceObservable(
        value=1.7493,
        tolerance=0.01,
        source="Planck 2018 distance-prior compression",
    ),
    "acoustic_scale_l_a": ReferenceObservable(
        value=301.47,
        tolerance=0.5,
        source="Planck 2018 distance-prior compression",
    ),
}


def compare_cmb_perturbations(
    observables: Mapping[str, float],
    *,
    reference: Mapping[str, ReferenceObservable] = PLANCK2018_CMB_REFERENCE,
) -> CompressedObservableReport:
    """Compare CMB compressed observables against deterministic reference rows."""

    return _compare(
        observable_set="cmb_perturbations",
        observables=observables,
        reference=reference,
        approximation_limit="compressed_cmb_reference_table_not_full_power_spectrum",
    )


def _compare(
    *,
    observable_set: str,
    observables: Mapping[str, float],
    reference: Mapping[str, ReferenceObservable],
    approximation_limit: str,
) -> CompressedObservableReport:
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
        observable_set=observable_set,
        status=status,
        comparisons=tuple(comparisons),
        failed_observables=tuple(failed),
        missing_observables=tuple(missing),
        approximation_limit=approximation_limit,
    )
