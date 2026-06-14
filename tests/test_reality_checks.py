from __future__ import annotations

from hubble_tension.schemas import DatasetChi2, H0Measurement, H0Relief, MetricPacket
from hubble_tension.schemas.metrics import LambdaCDMDelta
from hubble_tension.validation import (
    RealityChecker,
    can_use_packet_for_gate,
    default_dataset_registry,
    disguised_lambdacdm_promotable,
)


def test_default_likelihood_registry_covers_phase8_defaults() -> None:
    dataset_ids = {descriptor.dataset_id for descriptor in default_dataset_registry()}

    assert {
        "act_dr6",
        "bbn",
        "desi_bao",
        "legacy_bao",
        "local_h0_guardrail",
        "pantheon_plus",
        "planck_lite",
        "s8_guardrail",
        "sh0es",
        "spt_guardrail",
    } <= dataset_ids


def test_reality_checker_assigns_rejection_level_and_blocks_unknown_covariance() -> None:
    registry = default_dataset_registry()
    checker = RealityChecker(registry)
    packet = checker.screen_stub_model(hypothesis_id="hyp-1", wildness_level="W3")

    assert checker.rejection_level(packet) == "L2"
    assert can_use_packet_for_gate(packet, {item.dataset_id for item in registry[:5]})

    display_only = MetricPacket(
        chi2_min_by_dataset={
            "planck_lite": DatasetChi2(chi2=1.0, dof=1, n_data=1, status="ok")
        },
        best_fit_h0_by_dataset={
            "planck_lite": H0Measurement(value=67.4, sigma=0.5, source="fit")
        },
        h0_relief=H0Relief(
            early_late_gap_sigma_before=5.0,
            early_late_gap_sigma_after=5.0,
            delta_sigma=0.0,
            method="summary",
        ),
        wildness_level="W0",
    )
    assert not can_use_packet_for_gate(display_only, {"planck_lite"})


def test_disguised_lambda_cdm_is_not_promoted() -> None:
    packet = MetricPacket(
        chi2_min_by_dataset={},
        best_fit_h0_by_dataset={},
        covariance_policy="owned_observables",
        delta_vs_lambdacdm=LambdaCDMDelta(delta_chi2=0.0, status="ok"),
        h0_relief=H0Relief(
            early_late_gap_sigma_before=5.0,
            early_late_gap_sigma_after=5.0,
            delta_sigma=0.0,
            method="summary",
        ),
        wildness_level="W0",
    )

    assert disguised_lambdacdm_promotable(packet) is False
