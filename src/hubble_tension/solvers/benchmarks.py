from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from hubble_tension.schemas.metrics import MetricPacket

LAMBDA_CDM_REFERENCE = {
    "h0": 67.36,
    "omega_b_h2": 0.02237,
    "omega_cdm_h2": 0.1200,
}

LAMBDA_CDM_TOLERANCE = {
    "h0": 0.75,
    "omega_b_h2": 0.001,
    "omega_cdm_h2": 0.01,
}


@dataclass(frozen=True)
class ObservableReplayResult:
    status: str
    approximation_limit: str
    deviations: dict[str, float]
    failed_observables: tuple[str, ...]


def replay_lambdacdm_observables(observables: Mapping[str, float]) -> ObservableReplayResult:
    deviations: dict[str, float] = {}
    failed: list[str] = []
    for observable, reference in LAMBDA_CDM_REFERENCE.items():
        value = observables.get(observable)
        if value is None:
            failed.append(observable)
            continue
        deviation = abs(value - reference)
        deviations[observable] = round(deviation, 8)
        if deviation > LAMBDA_CDM_TOLERANCE[observable]:
            failed.append(observable)

    return ObservableReplayResult(
        status="failed_observable_replay" if failed else "passed_within_approximation",
        approximation_limit="phase10_fixture_reference",
        deviations=deviations,
        failed_observables=tuple(failed),
    )


def replay_ede_failure_mode(packet: MetricPacket) -> ObservableReplayResult:
    failures = [
        failure.observable
        for failure in packet.constraint_failures
        if failure.level in {"L2", "L3", "L4", "L5", "L6", "L7"}
    ]
    return ObservableReplayResult(
        status=(
            "ede_benchmark_failure_mode_reproduced"
            if failures
            else "ede_benchmark_failure_mode_missing"
        ),
        approximation_limit="phase10_fixture_failure_replay",
        deviations={},
        failed_observables=tuple(failures),
    )
