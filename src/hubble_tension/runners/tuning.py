from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from hubble_tension.state import ArtifactProvenance, StateStore

GENERATOR_QUARANTINE_WINDOW = 100
GENERATOR_QUARANTINE_THRESHOLD = 0.5
ABANDONMENT_THRESHOLDS = {
    "W0": 1,
    "W1": 2,
    "W2": 2,
    "W3": 3,
    "W4": 4,
    "W5": 5,
}


class ParameterSweeper:
    def sweep(self, parameter_bounds: Mapping[str, tuple[float, float]]) -> dict[str, float]:
        return {
            name: round((bounds[0] + bounds[1]) / 2.0, 6)
            for name, bounds in sorted(parameter_bounds.items())
        }


class BoundedOptimizer:
    def optimize(self, parameter_bounds: Mapping[str, tuple[float, float]]) -> dict[str, Any]:
        midpoint = ParameterSweeper().sweep(parameter_bounds)
        return {"best_parameters": midpoint, "status": "bounded_fixture_optimum"}


@dataclass(frozen=True)
class SearchCandidate:
    candidate_id: str
    parameters: dict[str, float]
    score: float
    generation: int
    strategy: str


class EvolutionarySearch:
    def __init__(
        self,
        objective: Callable[[Mapping[str, float]], float] | None = None,
    ) -> None:
        self.objective = objective

    def search(
        self,
        parameter_bounds: Mapping[str, tuple[float, float]],
        *,
        generations: int = 2,
        population_size: int = 4,
    ) -> list[SearchCandidate]:
        if generations < 1:
            raise ValueError("generations must be at least 1")
        if population_size < 1:
            raise ValueError("population_size must be at least 1")

        population = self._initial_population(parameter_bounds, population_size)
        candidates: list[SearchCandidate] = []
        for generation in range(generations):
            scored = [
                self._candidate(
                    parameters=parameters,
                    generation=generation,
                    slot=slot,
                    parameter_bounds=parameter_bounds,
                )
                for slot, parameters in enumerate(population)
            ]
            candidates.extend(scored)
            best = max(scored, key=lambda item: (item.score, item.candidate_id))
            population = self._next_population(
                best.parameters,
                parameter_bounds,
                generation=generation,
                population_size=population_size,
            )
        return candidates

    def _candidate(
        self,
        *,
        parameters: Mapping[str, float],
        generation: int,
        slot: int,
        parameter_bounds: Mapping[str, tuple[float, float]],
    ) -> SearchCandidate:
        normalized = {name: round(value, 6) for name, value in sorted(parameters.items())}
        return SearchCandidate(
            candidate_id=_stable_id(
                "search",
                str(generation),
                str(slot),
                json.dumps(normalized, sort_keys=True),
            ),
            parameters=normalized,
            score=round(self._score(normalized, parameter_bounds), 6),
            generation=generation,
            strategy="evolutionary_bounded",
        )

    def _initial_population(
        self,
        parameter_bounds: Mapping[str, tuple[float, float]],
        population_size: int,
    ) -> list[dict[str, float]]:
        population: list[dict[str, float]] = []
        for slot in range(population_size):
            fraction = 0.5 if population_size == 1 else slot / (population_size - 1)
            population.append(
                {
                    name: _interpolate(bounds, fraction)
                    for name, bounds in sorted(parameter_bounds.items())
                }
            )
        return population

    def _next_population(
        self,
        elite: Mapping[str, float],
        parameter_bounds: Mapping[str, tuple[float, float]],
        *,
        generation: int,
        population_size: int,
    ) -> list[dict[str, float]]:
        if population_size == 1:
            return [dict(elite)]
        denominator = max(population_size - 1, 1)
        shrink = 1.0 / float(generation + 2)
        midpoint_slot = denominator / 2.0
        population: list[dict[str, float]] = []
        for slot in range(population_size):
            offset = ((slot - midpoint_slot) / denominator) * shrink
            next_parameters: dict[str, float] = {}
            for name, bounds in sorted(parameter_bounds.items()):
                value = float(elite[name]) + (bounds[1] - bounds[0]) * offset
                next_parameters[name] = round(_cap(value, *bounds), 6)
            population.append(next_parameters)
        return population

    def _score(
        self,
        parameters: Mapping[str, float],
        parameter_bounds: Mapping[str, tuple[float, float]],
    ) -> float:
        if self.objective is not None:
            return self.objective(parameters)
        if not parameters:
            return 0.0
        penalties = []
        for name, value in parameters.items():
            lower, upper = parameter_bounds[name]
            span = upper - lower
            if span == 0.0:
                penalties.append(0.0)
                continue
            midpoint = (lower + upper) / 2.0
            penalties.append(abs(value - midpoint) / (span / 2.0))
        return max(0.0, 1.0 - (sum(penalties) / len(penalties)))


def mutate_formula_same_assumptions(equation: str) -> str:
    return equation.replace("alpha_zoroto", "min(alpha_zoroto, 1.0)")


@dataclass(frozen=True)
class BranchPriority:
    score: float
    novelty_tiebreaker: float
    hard_rejected: bool
    components: dict[str, float]


@dataclass(frozen=True)
class BacktrackingDecision:
    parent_hypothesis_id: str
    parent_checkpoint_id: str
    metric_packet_id: str
    rejection_level: str
    failed_observable: str
    reason: str
    evidence_json: dict[str, Any]


class BacktrackingPlanner:
    def plan(
        self,
        *,
        parent_hypothesis_id: str,
        parent_checkpoint_id: str,
        metric_packet_id: str,
        rejection_level: str,
        metric_evidence: Mapping[str, Any],
        rejection_evidence: Mapping[str, Any],
    ) -> BacktrackingDecision:
        if not parent_checkpoint_id:
            raise ValueError("parent_checkpoint_id is required for backtracking")
        if not metric_packet_id:
            raise ValueError("metric_packet_id is required for backtracking evidence")

        failed_observable = str(rejection_evidence.get("failed_observable", "unknown"))
        evidence_json = {
            "metric_evidence": dict(metric_evidence),
            "metric_packet_id": metric_packet_id,
            "rejection_evidence": dict(rejection_evidence),
            "rejection_level": rejection_level,
        }
        return BacktrackingDecision(
            parent_hypothesis_id=parent_hypothesis_id,
            parent_checkpoint_id=parent_checkpoint_id,
            metric_packet_id=metric_packet_id,
            rejection_level=rejection_level,
            failed_observable=failed_observable,
            reason=(
                "backtrack to checkpointed parent after "
                f"{metric_packet_id} failed {failed_observable} at {rejection_level}"
            ),
            evidence_json=evidence_json,
        )


def branch_priority(
    *,
    h0_relief_delta_sigma: float,
    constraint_penalty: float,
    compute_cost: float,
    novelty: float,
    hard_rejected: bool = False,
) -> BranchPriority:
    if hard_rejected:
        return BranchPriority(
            score=0.0,
            novelty_tiebreaker=0.0,
            hard_rejected=True,
            components={"hard_rejection_override": 1.0},
        )
    components = {
        "h0_relief": _cap(-h0_relief_delta_sigma, 0.0, 5.0) / 5.0,
        "constraint_penalty": _cap(constraint_penalty, 0.0, 5.0) / 5.0,
        "compute_cost": _cap(compute_cost, 0.0, 5.0) / 5.0,
    }
    score = components["h0_relief"] - components["constraint_penalty"] - components["compute_cost"]
    return BranchPriority(
        score=round(max(score, 0.0), 6),
        novelty_tiebreaker=round(_cap(novelty, 0.0, 1.0), 6),
        hard_rejected=False,
        components=components,
    )


class BranchManager:
    def __init__(self, store: StateStore, provenance: ArtifactProvenance) -> None:
        self.store = store
        self.provenance = provenance

    def record_same_assumption_tuning(
        self,
        *,
        tuning_event_id: str,
        hypothesis_id: str,
        branch_id: str,
        event_json: Mapping[str, Any],
    ) -> None:
        self.store.record_tuning_event(
            tuning_event_id=tuning_event_id,
            hypothesis_id=hypothesis_id,
            branch_id=branch_id,
            decision="continue",
            event_json={"same_assumption_set": True, **dict(event_json)},
            provenance=self.provenance,
        )

    def create_branch_for_assumption_change(
        self,
        *,
        parent_hypothesis_id: str,
        child_hypothesis_id: str,
        title: str,
        assumption_diff: Mapping[str, Any],
    ) -> str:
        self.store.insert_hypothesis(
            hypothesis_id=child_hypothesis_id,
            title=title,
            provenance=self.provenance,
            is_root_seed=False,
            parent_hypothesis_id=parent_hypothesis_id,
            status="screening_only_local_prior",
            hypothesis_json={"assumption_diff": dict(assumption_diff)},
        )
        edge_id = _stable_id("edge", parent_hypothesis_id, child_hypothesis_id)
        self.store.record_hypothesis_edge(
            edge_id=edge_id,
            source_hypothesis_id=parent_hypothesis_id,
            target_hypothesis_id=child_hypothesis_id,
            edge_type="assumption_changed_branch",
            rationale="assumption diff changed; created linked branch",
        )
        return edge_id

    def record_abandonment(
        self,
        *,
        tuning_event_id: str,
        hypothesis_id: str,
        branch_id: str,
        failed_level: str,
        failed_observable: str,
        lesson: str,
    ) -> None:
        self.store.record_tuning_event(
            tuning_event_id=tuning_event_id,
            hypothesis_id=hypothesis_id,
            branch_id=branch_id,
            decision="abandoned",
            event_json={
                "failed_level": failed_level,
                "failed_observable": failed_observable,
                "lesson": lesson,
            },
            provenance=self.provenance,
        )


@dataclass(frozen=True)
class GeneratorHealthRecord:
    generator_key: str
    agent_id: str
    agent_version_hash: str
    prompt_template_hash: str
    window_size: int
    l2_pass_count: int
    total_count: int
    rolling_l2_pass_rate: float
    status: str

    def as_json(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_version_hash": self.agent_version_hash,
            "generator_key": self.generator_key,
            "l2_pass_count": self.l2_pass_count,
            "prompt_template_hash": self.prompt_template_hash,
            "rolling_l2_pass_rate": self.rolling_l2_pass_rate,
            "status": self.status,
            "total_count": self.total_count,
            "window_size": self.window_size,
        }


@dataclass(frozen=True)
class QuarantineRoute:
    generator_key: str
    status: str
    route: str
    reason: str
    recovery_allowed: bool


class GeneratorHealthTracker:
    def evaluate(
        self,
        *,
        agent_id: str,
        agent_version_hash: str,
        prompt_template_hash: str,
        l2_passes: Sequence[bool],
    ) -> GeneratorHealthRecord:
        window = tuple(l2_passes[-GENERATOR_QUARANTINE_WINDOW:])
        total = len(window)
        passed = sum(1 for item in window if item)
        rate = 1.0 if total == 0 else passed / total
        status = (
            "generator_quarantine"
            if total and rate < GENERATOR_QUARANTINE_THRESHOLD
            else "healthy"
        )
        key_payload = {
            "agent_id": agent_id,
            "agent_version_hash": agent_version_hash,
            "prompt_template_hash": prompt_template_hash,
        }
        generator_key = hashlib.sha256(
            json.dumps(key_payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return GeneratorHealthRecord(
            generator_key=generator_key,
            agent_id=agent_id,
            agent_version_hash=agent_version_hash,
            prompt_template_hash=prompt_template_hash,
            window_size=GENERATOR_QUARANTINE_WINDOW,
            l2_pass_count=passed,
            total_count=total,
            rolling_l2_pass_rate=round(rate, 6),
            status=status,
        )


def generator_quarantine_route(
    health: GeneratorHealthRecord,
    *,
    automated_health_gate_passed: bool = False,
    versioned_config_migration: bool = False,
) -> QuarantineRoute:
    if health.status != "generator_quarantine":
        return QuarantineRoute(
            generator_key=health.generator_key,
            status=health.status,
            route="active_generation",
            reason="generator health is above quarantine threshold",
            recovery_allowed=True,
        )
    if automated_health_gate_passed or versioned_config_migration:
        status = (
            "cleared_by_versioned_config_migration"
            if versioned_config_migration
            else "recovered_by_automated_health_gate"
        )
        return QuarantineRoute(
            generator_key=health.generator_key,
            status=status,
            route="active_generation",
            reason="quarantine cleared by automated recovery condition",
            recovery_allowed=True,
        )
    return QuarantineRoute(
        generator_key=health.generator_key,
        status="generator_quarantine",
        route="deterministic_templates_and_calibration_replay_only",
        reason="rolling L2 pass rate fell below generator quarantine threshold",
        recovery_allowed=False,
    )


def abandonment_threshold(wildness_level: str) -> int:
    return ABANDONMENT_THRESHOLDS[wildness_level]


def _cap(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _interpolate(bounds: tuple[float, float], fraction: float) -> float:
    lower, upper = bounds
    return round(lower + ((upper - lower) * fraction), 6)


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"
