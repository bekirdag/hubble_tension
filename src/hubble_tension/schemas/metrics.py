from __future__ import annotations

from typing import Literal

from pydantic import Field

from hubble_tension.schemas.base import StrictBaseModel
from hubble_tension.schemas.candidates import NoveltyProfile
from hubble_tension.schemas.types import WildnessLevel


class DatasetChi2(StrictBaseModel):
    chi2: float | None = None
    dof: int | None = Field(default=None, ge=0)
    n_data: int | None = Field(default=None, ge=0)
    status: Literal["ok", "approximate", "failed", "not_run"]


class H0Measurement(StrictBaseModel):
    value: float | None = None
    sigma: float | None = Field(default=None, ge=0.0)
    units: str = "km/s/Mpc"
    source: Literal["fit", "summary_prior", "published_table", "not_available"]


class H0Relief(StrictBaseModel):
    early_late_gap_sigma_before: float | None = Field(default=None, ge=0.0)
    early_late_gap_sigma_after: float | None = Field(default=None, ge=0.0)
    delta_sigma: float | None = None
    method: Literal["summary", "joint_fit", "not_available"]


class JointChi2(StrictBaseModel):
    chi2: float | None = None
    dof: int | None = Field(default=None, ge=0)
    status: Literal["ok", "approximate", "failed", "not_run"]


class LambdaCDMDelta(StrictBaseModel):
    delta_chi2: float | None = None
    delta_aic: float | None = None
    delta_bic: float | None = None
    baseline_id: str = "lambda_cdm"
    status: Literal["ok", "approximate", "failed", "not_run"]


class ObservableShift(StrictBaseModel):
    value: float | None = None
    sigma: float | None = Field(default=None, ge=0.0)
    status: Literal["ok", "approximate", "failed", "not_run"]


class ConstraintFailure(StrictBaseModel):
    level: Literal["L0", "L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "L9"]
    dataset_id: str
    observable: str
    reason: str
    severity: Literal["hard", "soft", "inconclusive"]


class MetricPacket(StrictBaseModel):
    chi2_min_by_dataset: dict[str, DatasetChi2] = Field(default_factory=dict)
    best_fit_h0_by_dataset: dict[str, H0Measurement] = Field(default_factory=dict)
    covariance_policy: Literal["joint", "owned_observables", "display_only"] = "display_only"
    unknown_covariance_handling: Literal["display_only_unknown"] = "display_only_unknown"
    joint_chi2_min: JointChi2 = Field(
        default_factory=lambda: JointChi2(status="not_run")
    )
    delta_vs_lambdacdm: LambdaCDMDelta = Field(
        default_factory=lambda: LambdaCDMDelta(status="not_run")
    )
    h0_relief: H0Relief
    s8_shift: ObservableShift = Field(default_factory=lambda: ObservableShift(status="not_run"))
    rs_drag_shift: ObservableShift = Field(
        default_factory=lambda: ObservableShift(status="not_run")
    )
    constraint_failures: list[ConstraintFailure] = Field(default_factory=list)
    novelty_profile: NoveltyProfile | None = None
    wildness_level: WildnessLevel

    def validate_completeness(self, dataset_ids: set[str]) -> list[str]:
        missing: list[str] = []
        for dataset_id in sorted(dataset_ids):
            if dataset_id not in self.chi2_min_by_dataset:
                missing.append(f"missing chi2 for {dataset_id}")
            if dataset_id not in self.best_fit_h0_by_dataset:
                missing.append(f"missing H0 for {dataset_id}")
        if (
            self.covariance_policy == "display_only"
            and self.unknown_covariance_handling == "display_only_unknown"
        ):
            missing.append("display-only unknown covariance cannot be used for gates")
        return missing
