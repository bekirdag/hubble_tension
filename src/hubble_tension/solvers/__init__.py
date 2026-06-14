"""Supported solver and posterior integration scaffolding."""

from hubble_tension.solvers.adapter import CandidateSolverAdapter, SolverRequest
from hubble_tension.solvers.benchmarks import (
    ObservableReplayResult,
    replay_ede_failure_mode,
    replay_lambdacdm_observables,
)
from hubble_tension.solvers.environment import (
    SolverEnvironmentConfig,
    SolverProbeResult,
    SolverSource,
    probe_solver_environment,
    read_solver_config,
    solver_package_status,
)
from hubble_tension.solvers.posterior import PosteriorResult, PosteriorRunner

__all__ = [
    "CandidateSolverAdapter",
    "ObservableReplayResult",
    "PosteriorResult",
    "PosteriorRunner",
    "SolverEnvironmentConfig",
    "SolverProbeResult",
    "SolverRequest",
    "SolverSource",
    "probe_solver_environment",
    "read_solver_config",
    "replay_ede_failure_mode",
    "replay_lambdacdm_observables",
    "solver_package_status",
]
