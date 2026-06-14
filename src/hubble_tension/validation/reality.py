from __future__ import annotations

from collections.abc import Sequence

from hubble_tension.schemas.metrics import (
    ConstraintFailure,
    DatasetChi2,
    H0Measurement,
    H0Relief,
    JointChi2,
    LambdaCDMDelta,
    MetricPacket,
    ObservableShift,
)
from hubble_tension.schemas.types import WildnessLevel
from hubble_tension.validation.likelihoods import DatasetDescriptor


class RealityChecker:
    """Deterministic L0-L5 summary screen for generated model fixtures."""

    def __init__(self, dataset_registry: Sequence[DatasetDescriptor]) -> None:
        self.dataset_registry = tuple(dataset_registry)

    def screen_stub_model(
        self,
        *,
        hypothesis_id: str,
        wildness_level: WildnessLevel,
    ) -> MetricPacket:
        del hypothesis_id
        datasets = {descriptor.dataset_id for descriptor in self.dataset_registry[:5]}
        return MetricPacket(
            chi2_min_by_dataset={
                dataset_id: DatasetChi2(chi2=1.0, dof=1, n_data=1, status="approximate")
                for dataset_id in datasets
            },
            best_fit_h0_by_dataset={
                "planck_lite": H0Measurement(value=68.0, sigma=0.6, source="summary_prior"),
                "desi_bao": H0Measurement(value=68.5, sigma=1.0, source="summary_prior"),
                "legacy_bao": H0Measurement(value=68.2, sigma=1.1, source="summary_prior"),
                "pantheon_plus": H0Measurement(value=70.0, sigma=1.5, source="summary_prior"),
                "sh0es": H0Measurement(value=73.0, sigma=1.0, source="summary_prior"),
                "bbn": H0Measurement(value=67.8, sigma=1.2, source="summary_prior"),
            },
            covariance_policy="owned_observables",
            unknown_covariance_handling="display_only_unknown",
            joint_chi2_min=JointChi2(chi2=5.0, dof=5, status="approximate"),
            delta_vs_lambdacdm=LambdaCDMDelta(
                delta_chi2=-0.5,
                delta_aic=1.5,
                delta_bic=2.5,
                status="approximate",
            ),
            h0_relief=H0Relief(
                early_late_gap_sigma_before=5.0,
                early_late_gap_sigma_after=4.2,
                delta_sigma=-0.8,
                method="summary",
            ),
            s8_shift=ObservableShift(value=0.02, sigma=0.5, status="approximate"),
            rs_drag_shift=ObservableShift(value=-0.08, sigma=0.4, status="approximate"),
            constraint_failures=[
                ConstraintFailure(
                    level="L2",
                    dataset_id="desi_bao",
                    observable="per_dataset_h0_consistency",
                    reason="late and early summaries still prefer separated H0 values",
                    severity="soft",
                )
            ],
            wildness_level=wildness_level,
        )

    def rejection_level(self, packet: MetricPacket) -> str:
        if packet.validate_completeness({item.dataset_id for item in self.dataset_registry[:5]}):
            return "L0"
        hard_failures = [
            failure for failure in packet.constraint_failures if failure.severity == "hard"
        ]
        if hard_failures:
            return hard_failures[0].level
        if packet.constraint_failures:
            return packet.constraint_failures[0].level
        if packet.h0_relief.delta_sigma is not None and packet.h0_relief.delta_sigma >= 0:
            return "L3"
        return "L5"


def disguised_lambdacdm_promotable(packet: MetricPacket) -> bool:
    delta = packet.delta_vs_lambdacdm
    if delta.delta_chi2 is None:
        return False
    return not (-0.1 <= delta.delta_chi2 <= 0.1)


def can_use_packet_for_gate(packet: MetricPacket, dataset_ids: set[str]) -> bool:
    return not packet.validate_completeness(dataset_ids)
