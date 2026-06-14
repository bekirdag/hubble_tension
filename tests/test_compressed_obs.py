from __future__ import annotations

from hubble_tension.compressed_obs import (
    HYREC2_RECOMBINATION_REFERENCE,
    PLANCK2018_CMB_REFERENCE,
    compare_cmb_perturbations,
    compare_recombination_history,
)


def test_cmb_perturbation_reference_table_passes_planck_fixture() -> None:
    report = compare_cmb_perturbations(
        {name: row.value for name, row in PLANCK2018_CMB_REFERENCE.items()}
    )

    assert report.passed()
    assert report.status == "passed_reference_table"
    assert report.observable_set == "cmb_perturbations"
    assert report.approximation_limit == "compressed_cmb_reference_table_not_full_power_spectrum"
    assert all("Planck 2018" in comparison.source for comparison in report.comparisons)


def test_cmb_perturbation_reference_table_records_failure_and_missing() -> None:
    report = compare_cmb_perturbations({"theta_s_100": 2.0})

    assert not report.passed()
    assert report.status == "missing_observable"
    assert "theta_s_100" in report.failed_observables
    assert "shift_parameter_r" in report.missing_observables
    assert "acoustic_scale_l_a" in report.missing_observables


def test_recombination_reference_table_passes_hyrec_fixture() -> None:
    report = compare_recombination_history(
        {name: row.value for name, row in HYREC2_RECOMBINATION_REFERENCE.items()}
    )

    assert report.passed()
    assert report.status == "passed_reference_table"
    assert report.observable_set == "recombination_history"
    assert report.approximation_limit == "hyrec2_fixture_not_full_recombination_solver"
    assert all("HyRec-2" in comparison.source for comparison in report.comparisons)


def test_recombination_reference_table_records_failure_and_missing() -> None:
    report = compare_recombination_history({"z_rec": 900.0})

    assert not report.passed()
    assert report.status == "missing_observable"
    assert "z_rec" in report.failed_observables
    assert "tau_rec" in report.missing_observables
    assert "sigma_rec" in report.missing_observables
