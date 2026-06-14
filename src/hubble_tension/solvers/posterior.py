from __future__ import annotations

from dataclasses import dataclass

from hubble_tension.runtime.config import BudgetConfig
from hubble_tension.solvers.adapter import SolverRequest
from hubble_tension.solvers.environment import BOOTSTRAP_SOLVER_UNAVAILABLE


@dataclass(frozen=True)
class PosteriorResult:
    candidate_id: str
    status: str
    sampler: str
    reason: str
    blocks_stable_candidate: bool
    next_route: str


class PosteriorRunner:
    def __init__(self, *, sampler: str = "cobaya") -> None:
        self.sampler = sampler

    def run(
        self,
        request: SolverRequest,
        *,
        budget: BudgetConfig,
        likelihoods_installed: bool,
        elapsed_hours: float,
        solver_available: bool = True,
        converged: bool = True,
        crashed: bool = False,
    ) -> PosteriorResult:
        if request.status == "phenomenological_background":
            return self._blocked(
                request,
                status="phenomenological_background",
                reason="candidate has no supported perturbation/recombination solver path",
                next_route="background_screening_only",
            )
        if not solver_available:
            return self._blocked(
                request,
                status=BOOTSTRAP_SOLVER_UNAVAILABLE,
                reason="required solver backend is unavailable",
                next_route="bootstrap_solver_environment",
            )
        if crashed:
            return self._blocked(
                request,
                status="solver_crash",
                reason="solver runtime crashed during posterior setup",
                next_route="backtrack_or_simplify_model",
            )
        if not likelihoods_installed:
            return self._blocked(
                request,
                status="missing_likelihoods",
                reason="public likelihood packages are not installed",
                next_route="screen_more_or_bootstrap_likelihoods",
            )
        if not converged:
            return self._blocked(
                request,
                status="non_convergence",
                reason="posterior sampler did not converge",
                next_route="simplify_or_backtrack",
            )
        if elapsed_hours >= budget.l7_posterior_attempt_hours:
            return self._blocked(
                request,
                status=budget.l7_timeout_status,
                reason="local L7 posterior attempt timed out",
                next_route="screen_more_simplify_or_future_compute",
            )
        return PosteriorResult(
            candidate_id=request.candidate_id,
            status="posterior_comparison_ready",
            sampler=self.sampler,
            reason="posterior wrapper is ready for supported likelihood comparison",
            blocks_stable_candidate=True,
            next_route="run_full_supported_posterior",
        )

    def _blocked(
        self,
        request: SolverRequest,
        *,
        status: str,
        reason: str,
        next_route: str,
    ) -> PosteriorResult:
        return PosteriorResult(
            candidate_id=request.candidate_id,
            status=status,
            sampler=self.sampler,
            reason=reason,
            blocks_stable_candidate=True,
            next_route=next_route,
        )
