from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from hubble_tension.runtime.config import read_budget_config
from hubble_tension.schemas import (
    ConstraintFailure,
    H0Relief,
    MetricPacket,
)
from hubble_tension.schemas.candidates import CandidateRecord
from hubble_tension.solvers import (
    CandidateSolverAdapter,
    PosteriorRunner,
    probe_solver_environment,
    read_solver_config,
    replay_ede_failure_mode,
    replay_lambdacdm_observables,
    solver_package_status,
)


def test_solver_config_records_supported_phase10_environment() -> None:
    config = read_solver_config(Path("config/solvers.yaml"))

    assert config.image == "hubble-tension-solvers:phase10"
    assert config.compiler == "gcc-13"
    assert config.openmp == "libgomp"
    assert config.blas == "openblas"
    assert config.default_sampler == "cobaya"
    assert config.fallback_sampler == "montepython"
    assert config.timeout_status == "inconclusive_posterior"
    assert {source.name for source in config.required_sources} == {"class", "hyrec2"}
    assert {source.pinned_ref_kind for source in config.sources} == {"commit"}
    assert {source.pinned_ref_verified_at for source in config.sources} == {"2026-06-14"}
    assert all(len(source.pinned_ref) == 40 for source in config.sources)
    assert {source.name: source.pinned_ref for source in config.sources} == {
        "axiclass": "ba4ede7b1d735aa6312ab5f4355d26b5e617e70c",
        "class": "e85808324f51fc694d12e3ed7439552a3c3f9540",
        "class_ede": "5a131c91d657dd9a7c6364cc45b038710f8d0d97",
        "hyrec2": "09e8243d0e08edd3603a94dfbc445ae06cafe139",
    }
    assert {source.required_ref_env for source in config.sources} == {
        "HT_AXICLASS_REF",
        "HT_CLASS_EDE_REF",
        "HT_CLASS_REF",
        "HT_HYREC2_REF",
    }


def test_solver_probe_is_lazy_then_surfaces_bootstrap_failure(tmp_path: Path) -> None:
    pending = solver_package_status(repo_root=Path("."), env={})
    config = read_solver_config(Path("config/solvers.yaml"))
    failed = probe_solver_environment(
        config=config,
        repo_root=Path("."),
        env={"HT_SOLVER_PREFIX": str(tmp_path), "HT_LAB_ENABLE_SOLVER_PROBE": "1"},
    )

    assert pending.status == "integration_pending"
    assert pending.source_pins["class"] == "e85808324f51fc694d12e3ed7439552a3c3f9540"
    assert failed.status == "bootstrap_solver_unavailable"
    assert failed.as_state()["source_pins"] == pending.as_state()["source_pins"]
    assert failed.missing_sources == ("class", "hyrec2")
    assert "HT_CLASS_REF" in failed.required_ref_envs


def test_candidate_adapter_maps_supported_and_phenomenological_families() -> None:
    candidate = CandidateRecord.model_validate(
        json.loads(Path("tests/fixtures/fake_stable_candidate.json").read_text())
    )
    request = CandidateSolverAdapter().adapt(
        candidate,
        model_family="early_dark_energy",
        parameters={"f_ede": 0.05},
    )
    wild_candidate = candidate.model_copy(
        update={"candidate_id": "cand-w5", "wildness_level": "W5"}
    )
    phenomenological = CandidateSolverAdapter().adapt(
        wild_candidate,
        model_family="parallel_time_flow",
    )

    assert request.status == "solver_request_ready"
    assert request.required_sources == ("class", "class_ede")
    assert request.solver_backend == "class_ede"
    assert request.parameters == {"f_ede": 0.05}
    assert phenomenological.status == "phenomenological_background"
    assert phenomenological.solver_backend is None


def test_lambda_cdm_and_ede_benchmark_replay_contracts() -> None:
    baseline = replay_lambdacdm_observables(
        {"h0": 67.4, "omega_b_h2": 0.0224, "omega_cdm_h2": 0.121}
    )
    ede_packet = MetricPacket(
        h0_relief=H0Relief(
            early_late_gap_sigma_before=5.0,
            early_late_gap_sigma_after=4.4,
            delta_sigma=-0.6,
            method="summary",
        ),
        constraint_failures=[
            ConstraintFailure(
                level="L2",
                dataset_id="desi_bao",
                observable="bao_consistency",
                reason="EDE-like relief worsened BAO summary consistency",
                severity="soft",
            )
        ],
        wildness_level="W1",
    )
    ede = replay_ede_failure_mode(ede_packet)

    assert baseline.status == "passed_within_approximation"
    assert baseline.failed_observables == ()
    assert ede.status == "ede_benchmark_failure_mode_reproduced"
    assert ede.failed_observables == ("bao_consistency",)


def test_posterior_runner_blocks_stable_candidate_on_timeout_and_failures() -> None:
    candidate = CandidateRecord.model_validate(
        json.loads(Path("tests/fixtures/fake_stable_candidate.json").read_text())
    )
    request = CandidateSolverAdapter().adapt(candidate, model_family="lambda_cdm")
    budget = read_budget_config(Path("config/budgets.yaml"))
    runner = PosteriorRunner(sampler="cobaya")

    timeout = runner.run(
        request,
        budget=budget,
        likelihoods_installed=True,
        elapsed_hours=12.0,
    )
    missing = runner.run(
        request,
        budget=budget,
        likelihoods_installed=False,
        elapsed_hours=1.0,
    )
    crash = runner.run(
        request,
        budget=budget,
        likelihoods_installed=True,
        elapsed_hours=1.0,
        crashed=True,
    )
    non_converged = runner.run(
        request,
        budget=budget,
        likelihoods_installed=True,
        elapsed_hours=1.0,
        converged=False,
    )

    assert timeout.status == "inconclusive_posterior"
    assert timeout.blocks_stable_candidate is True
    assert timeout.next_route == "screen_more_simplify_or_future_compute"
    assert missing.status == "missing_likelihoods"
    assert crash.status == "solver_crash"
    assert non_converged.status == "non_convergence"


def test_solver_build_script_dry_run_and_missing_pin_failure(tmp_path: Path) -> None:
    dry_run = subprocess.run(
        ["bash", "tools/build_solvers.sh", "--dry-run", "--prefix", str(tmp_path)],
        check=True,
        text=True,
        capture_output=True,
    )
    failure = subprocess.run(
        ["bash", "tools/build_solvers.sh", "--prefix", str(tmp_path)],
        check=False,
        text=True,
        capture_output=True,
        env={**os.environ, "HT_SOLVER_DISABLE_DEFAULT_PINS": "1"},
    )
    container_dry_run = subprocess.run(
        ["bash", "tools/build_solvers.sh", "--dry-run", "--container-build"],
        check=True,
        text=True,
        capture_output=True,
    )

    assert "solver build plan:" in dry_run.stdout
    assert "e85808324f51fc694d12e3ed7439552a3c3f9540" in dry_run.stdout
    assert "class_public.git" in dry_run.stdout
    assert "HYREC-2.git" in dry_run.stdout
    assert "tools/Containerfile.solvers" in container_dry_run.stdout
    assert "HT_CLASS_REF=e85808324f51fc694d12e3ed7439552a3c3f9540" in container_dry_run.stdout
    assert failure.returncode == 42
    assert "bootstrap_solver_unavailable" in failure.stderr
