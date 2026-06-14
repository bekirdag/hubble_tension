from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hubble_tension.concept_forge.forge import ConceptForge, PriorArtChecker
from hubble_tension.corpus.importer import load_corpus
from hubble_tension.equations.builder import EquationBuilder, MathCritic
from hubble_tension.generated_models.renderer import GeneratedModelRenderer
from hubble_tension.lab.agents import LabHeadSelection
from hubble_tension.runners.sandbox import SandboxRunner
from hubble_tension.runners.tuning import BranchManager, GeneratorHealthTracker, ParameterSweeper
from hubble_tension.runtime.logging import LabLogger, LogContext
from hubble_tension.runtime.state import JsonObject
from hubble_tension.state import StateStore
from hubble_tension.validation.likelihoods import default_dataset_registry
from hubble_tension.validation.reality import RealityChecker

STAGES = (
    "observe",
    "imagine",
    "hypothesize",
    "formalize",
    "implement",
    "test",
    "tune",
    "branch_backtrack_refute",
    "remember",
    "restart",
)


@dataclass(frozen=True)
class StubLabLoopResult:
    status: str
    hypothesis_id: str
    model_id: str
    implementation_path: str
    decision_id: str
    stages: tuple[str, ...]


class StubLabLoop:
    """Deterministic end-to-end lab loop used before real science engines are ready."""

    def __init__(
        self,
        *,
        repo_root: Path,
        run_dir: Path,
        state_store: StateStore,
        lab_head: LabHeadSelection,
        logger: LabLogger,
        context: LogContext,
        env: Mapping[str, str],
    ) -> None:
        self.repo_root = repo_root
        self.run_dir = run_dir
        self.state_store = state_store
        self.lab_head = lab_head
        self.logger = logger
        self.context = context
        self.env = env
        self.fixture = _load_fixture("stub_lab_head.json")

    def run_once(self, state: JsonObject) -> StubLabLoopResult:
        corpus = self._stage_observe(state)
        concept = self._stage_imagine(state, corpus)
        hypothesis_id = self._stage_hypothesize(state, concept)
        model_id, equations = self._stage_formalize(state, hypothesis_id, concept)
        implementation_path = self._stage_implement(state, hypothesis_id, model_id, equations)
        packet, test_status = self._stage_test(state, hypothesis_id, implementation_path)
        self._stage_tune(state, hypothesis_id, packet)
        self._stage_branch_backtrack_refute(state, hypothesis_id, packet)
        self._stage_remember(state, hypothesis_id, test_status)
        decision_id = self._stage_restart(state, hypothesis_id, packet)

        state["status"] = "ready"
        return StubLabLoopResult(
            status="ready",
            hypothesis_id=hypothesis_id,
            model_id=model_id,
            implementation_path=implementation_path,
            decision_id=decision_id,
            stages=STAGES,
        )

    def _stage_observe(self, state: JsonObject) -> dict[str, Any]:
        self._record_stage(state, "observe", "loading corpus context")
        source = self.env.get("HT_LAB_CORPUS_SOURCE", "real")
        if source == "mock":
            return _load_fixture("mock_corpus.json")

        imported = load_corpus(self.repo_root)
        return {
            "source": "real",
            "dataset_ids": [lead.dataset_id for lead in imported.dataset_leads],
            "papers": [
                {
                    "paper_id": paper.paper_id,
                    "title": paper.title,
                    "category": paper.category,
                    "datasets": paper.metadata.get("dataset_hints", []),
                }
                for paper in imported.papers[:25]
            ],
            "failure_memory": [],
        }

    def _stage_imagine(self, state: JsonObject, corpus: Mapping[str, Any]) -> dict[str, Any]:
        self._record_stage(state, "imagine", "creating deterministic concept seeds")
        forge = ConceptForge(seed=17)
        candidates = forge.generate(corpus)
        checker = PriorArtChecker(corpus)
        selected = next(candidate for candidate in candidates if candidate.wildness_level == "W3")
        prior_art = checker.check(selected)
        self.state_store.insert_concept_seed(
            seed_id=selected.seed_id,
            source_kind=selected.source_kind,
            source_ref=selected.source_ref,
            concept_text=selected.concept_text,
            wildness_level=selected.wildness_level,
            provenance=self.lab_head.provenance,
        )
        self.state_store.record_prior_art_check(
            check_id=f"prior-{selected.seed_id}",
            verdict=prior_art["verdict"],
            prior_art_json=prior_art,
            provenance=self.lab_head.provenance,
            concept_seed_id=selected.seed_id,
        )
        return selected.as_hypothesis_json()

    def _stage_hypothesize(self, state: JsonObject, concept: Mapping[str, Any]) -> str:
        self._record_stage(state, "hypothesize", "writing hypothesis and assumptions")
        hypothesis_id = "hyp-stub-zoroto-000001"
        assumption_set_id = "assumption-stub-zoroto-000001"
        assumption_diff = _dict(concept["assumption_diff"])
        self.state_store.insert_assumption_set(
            assumption_set_id=assumption_set_id,
            assumptions_json={"active": ["general_relativity", "zoroto_screening_field"]},
            diff_json=assumption_diff,
            provenance=self.lab_head.provenance,
            hypothesis_id=hypothesis_id,
        )
        self.state_store.insert_hypothesis(
            hypothesis_id=hypothesis_id,
            title=str(concept["title"]),
            provenance=self.lab_head.provenance,
            is_root_seed=True,
            status="screening_only_local_prior",
            hypothesis_json=dict(concept),
            assumption_set_id=assumption_set_id,
            concept_seed_id=str(concept["seed_id"]),
        )
        state["active_hypothesis_id"] = hypothesis_id
        return hypothesis_id

    def _stage_formalize(
        self,
        state: JsonObject,
        hypothesis_id: str,
        concept: Mapping[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        self._record_stage(state, "formalize", "building and critiquing stub equations")
        model_id = "model-stub-zoroto-000001"
        equations = EquationBuilder().build(concept)
        critique = MathCritic().review(equations)
        self.state_store.insert_formal_model(
            model_id=model_id,
            hypothesis_id=hypothesis_id,
            equations_json=equations,
            model_json={"math_critic": critique, "family_label": "unchecked_or_phenomenological"},
            provenance=self.lab_head.provenance,
        )
        return model_id, equations

    def _stage_implement(
        self,
        state: JsonObject,
        hypothesis_id: str,
        model_id: str,
        equations: Mapping[str, Any],
    ) -> str:
        self._record_stage(state, "implement", "generating harmless model module")
        renderer = GeneratedModelRenderer()
        output_dir = self.run_dir / "generated_models"
        rendered = renderer.write_module(
            output_dir=output_dir,
            module_name="stub_zoroto_model",
            equations=equations,
            provenance=self.lab_head.provenance,
        )
        self.state_store.insert_implementation(
            implementation_id="impl-stub-zoroto-000001",
            hypothesis_id=hypothesis_id,
            model_id=model_id,
            path=str(rendered.path),
            code_hash=rendered.code_hash,
            status="generated",
            provenance=self.lab_head.provenance,
        )
        return str(rendered.path)

    def _stage_test(
        self,
        state: JsonObject,
        hypothesis_id: str,
        implementation_path: str,
    ) -> tuple[Any, str]:
        self._record_stage(state, "test", "running sandbox static checks and reality screen")
        sandbox = SandboxRunner(runtime_name=self.env.get("HT_LAB_SANDBOX_RUNTIME", "podman"))
        sandbox_result = sandbox.run_static_checks(Path(implementation_path))
        checker = RealityChecker(default_dataset_registry())
        packet = checker.screen_stub_model(hypothesis_id=hypothesis_id, wildness_level="W3")
        self.state_store.record_metric_packet(
            metric_packet_id="metric-stub-zoroto-000001",
            hypothesis_id=hypothesis_id,
            packet_json=packet.model_dump(mode="json"),
            provenance=self.lab_head.provenance,
        )
        state["last_metric_packet_id"] = "metric-stub-zoroto-000001"
        return packet, sandbox_result.status

    def _stage_tune(self, state: JsonObject, hypothesis_id: str, packet: Any) -> None:
        self._record_stage(state, "tune", "sweeping bounded stub parameters")
        sweep = ParameterSweeper().sweep(
            parameter_bounds={"alpha_zoroto": (0.0, 1.0), "z_transition": (500.0, 5000.0)}
        )
        self.state_store.record_tuning_event(
            tuning_event_id="tune-stub-zoroto-000001",
            hypothesis_id=hypothesis_id,
            branch_id=str(state.get("active_branch_id", "branch-000000")),
            decision="continue",
            event_json={"sweep": sweep, "h0_relief": packet.h0_relief.model_dump()},
            provenance=self.lab_head.provenance,
        )

    def _stage_branch_backtrack_refute(
        self,
        state: JsonObject,
        hypothesis_id: str,
        packet: Any,
    ) -> None:
        self._record_stage(
            state,
            "branch_backtrack_refute",
            "creating branch evidence and abandoned lesson",
        )
        manager = BranchManager(self.state_store, self.lab_head.provenance)
        manager.record_abandonment(
            tuning_event_id="abandon-stub-zoroto-000001",
            hypothesis_id=hypothesis_id,
            branch_id=str(state.get("active_branch_id", "branch-000000")),
            failed_level="L2",
            failed_observable="bao_h0_consistency",
            lesson="H0 relief must be checked against per-dataset best-fit H0 agreement.",
        )
        health = GeneratorHealthTracker().evaluate(
            agent_id=self.lab_head.agent_id,
            agent_version_hash=self.lab_head.agent_version_hash,
            prompt_template_hash=self.lab_head.prompt_template_hash,
            l2_passes=[False],
        )
        self.state_store.record_generator_health(health)

    def _stage_remember(self, state: JsonObject, hypothesis_id: str, test_status: str) -> None:
        self._record_stage(state, "remember", "writing searchable lab note")
        self.state_store.append_lab_note(
            note_id="note-stub-zoroto-000001",
            hypothesis_id=hypothesis_id,
            note_type="phase5_stub_cycle",
            content=(
                "Stub lab cycle created zoroto screening field, generated a safe module, "
                f"ran static sandbox checks with status {test_status}, and recorded an L2 lesson."
            ),
            provenance=self.lab_head.provenance,
        )

    def _stage_restart(self, state: JsonObject, hypothesis_id: str, packet: Any) -> str:
        self._record_stage(state, "restart", "recording lab-head next-step decision")
        decision_id = "decision-stub-zoroto-000001"
        fixture_decision = _dict(self.fixture["decision"])
        self.state_store.record_lab_head_decision(
            decision_id=decision_id,
            hypothesis_id=hypothesis_id,
            decision=str(fixture_decision["decision"]),
            rationale=str(fixture_decision["rationale"]),
            uncertainty=str(fixture_decision["uncertainty"]),
            observation_json={
                "h0_relief": packet.h0_relief.model_dump(mode="json"),
                "constraint_failures": [
                    failure.model_dump(mode="json") for failure in packet.constraint_failures
                ],
            },
            actions_json={"next_checkpoint": "restart_from_checkpoint"},
            next_step=str(fixture_decision["next_step"]),
            provenance=self.lab_head.provenance,
        )
        state["last_lab_head_decision_id"] = decision_id
        return decision_id

    def _record_stage(self, state: JsonObject, stage: str, message: str) -> None:
        self.logger.emit(self.context, stage, message)
        lab_loop = state.setdefault("lab_loop", {})
        if isinstance(lab_loop, dict):
            history = lab_loop.setdefault("stage_history", [])
            if isinstance(history, list):
                history.append(stage)


def _load_fixture(filename: str) -> dict[str, Any]:
    path = Path(__file__).resolve().parent / "fixtures" / filename
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"fixture must decode to object: {filename}")
    return payload


def _dict(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("expected object payload")
    return value
