from __future__ import annotations

import hashlib
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from hubble_tension.schemas.assumptions import AssumptionDiff
from hubble_tension.schemas.types import WildnessLevel

WildnessLiteral = Literal["W0", "W1", "W2", "W3", "W4", "W5"]

BASE_ASSUMPTIONS = (
    "dark_matter",
    "dark_energy",
    "flatness",
    "standard_recombination",
    "general_relativity",
    "monotonic_time_evolution",
)


@dataclass(frozen=True)
class ConceptCandidate:
    seed_id: str
    source_kind: str
    source_ref: str | None
    concept_text: str
    wildness_level: WildnessLevel
    seed: int
    operators: tuple[str, ...]
    parameter_budget: int
    assumption_diff: AssumptionDiff
    falsification_tests: tuple[str, ...]
    reason_for_queue_entry: str
    fiction_inspiration_only: bool = False

    def as_hypothesis_json(self) -> dict[str, Any]:
        concept_name = self.concept_text.split(" that ", 1)[0].replace("Assume ", "")
        if len(concept_name) > 72:
            concept_name = concept_name[:72].rstrip()
        return {
            "assumption_diff": self.assumption_diff.model_dump(mode="json"),
            "concept_name": concept_name,
            "concept_text": self.concept_text,
            "falsification_tests": list(self.falsification_tests),
            "fiction_inspiration_only": self.fiction_inspiration_only,
            "operators": list(self.operators),
            "parameter_budget": self.parameter_budget,
            "reason_for_queue_entry": self.reason_for_queue_entry,
            "seed": self.seed,
            "seed_id": self.seed_id,
            "source_kind": self.source_kind,
            "source_ref": self.source_ref,
            "title": _title_from_concept(self.concept_text),
            "wildness_level": self.wildness_level,
        }


class ConceptForge:
    """Deterministic concept generator spanning grounded and speculative tracks."""

    def __init__(self, *, seed: int) -> None:
        self.seed = seed

    def generate(self, corpus: Mapping[str, Any]) -> tuple[ConceptCandidate, ...]:
        rng = random.Random(self.seed)
        papers = _paper_items(corpus)
        paper_ref = _paper_id(papers[0]) if papers else "paper-unknown"
        return (
            self._paper_mutation(paper_ref),
            self._failure_inversion(paper_ref),
            self._assumption_removal("dark_energy", "W2"),
            self._assumption_addition(paper_ref),
            self._random_grammar(rng, "W4"),
        )

    def _paper_mutation(self, paper_ref: str | None) -> ConceptCandidate:
        return ConceptCandidate(
            seed_id="seed-forge-w0-paper-mutation",
            source_kind="paper_mutation",
            source_ref=paper_ref,
            concept_text=(
                "Assume early-dark-energy decay is delayed only in the sound-horizon "
                "integral but constrained by BAO consistency"
            ),
            wildness_level="W0",
            seed=self.seed,
            operators=("paper_mutation",),
            parameter_budget=2,
            assumption_diff=AssumptionDiff(
                kept=["dark_matter", "dark_energy", "general_relativity"],
                modified=["pre_recombination_expansion_history"],
            ),
            falsification_tests=_default_falsification_tests(),
            reason_for_queue_entry="grounded replay mutation from scanned early-universe papers",
        )

    def _failure_inversion(self, paper_ref: str | None) -> ConceptCandidate:
        return ConceptCandidate(
            seed_id="seed-forge-w1-failure-inversion",
            source_kind="failure_inversion",
            source_ref=paper_ref,
            concept_text=(
                "Assume the no-go BAO mismatch is the primary signal and invert the "
                "model to penalize inconsistent per-dataset H0"
            ),
            wildness_level="W1",
            seed=self.seed,
            operators=("failure_inversion",),
            parameter_budget=2,
            assumption_diff=AssumptionDiff(
                kept=["flatness", "general_relativity"],
                modified=["bao_consistency_weight"],
            ),
            falsification_tests=_default_falsification_tests(),
            reason_for_queue_entry="uses stored no-go lessons as a generator input",
        )

    def _assumption_removal(
        self,
        assumption: str,
        wildness_level: WildnessLiteral,
    ) -> ConceptCandidate:
        return ConceptCandidate(
            seed_id=f"seed-forge-{wildness_level.lower()}-remove-{assumption}",
            source_kind="assumption_removal",
            source_ref=assumption,
            concept_text=f"Assume {assumption} is not fundamental and fit the summaries without it",
            wildness_level=wildness_level,
            seed=self.seed,
            operators=("assumption_removal",),
            parameter_budget=4,
            assumption_diff=AssumptionDiff(
                kept=[item for item in BASE_ASSUMPTIONS if item != assumption],
                removed=[assumption],
            ),
            falsification_tests=_default_falsification_tests(),
            reason_for_queue_entry=f"explicit SDS track removing {assumption}",
        )

    def _assumption_addition(self, paper_ref: str | None) -> ConceptCandidate:
        return ConceptCandidate(
            seed_id="seed-forge-w3-zoroto-screening",
            source_kind="paper_mutation",
            source_ref=paper_ref,
            concept_text=(
                "Assume zoroto screening field that interacts before recombination "
                "and vanishes before distance-ladder calibration"
            ),
            wildness_level="W3",
            seed=self.seed,
            operators=("paper_mutation", "assumption_addition", "failure_inversion"),
            parameter_budget=3,
            assumption_diff=AssumptionDiff(
                kept=["general_relativity", "statistical_isotropy"],
                added=["zoroto_screening_field"],
                modified=["pre_recombination_expansion_history"],
            ),
            falsification_tests=_default_falsification_tests(),
            reason_for_queue_entry="speculative paper-inspired branch with prior-art requirement",
        )

    def _random_grammar(
        self,
        rng: random.Random,
        wildness_level: WildnessLiteral,
    ) -> ConceptCandidate:
        invented = rng.choice(("caloro", "nexial", "virel"))
        mechanism = rng.choice(("time-flow", "hidden-sector", "parallel-background"))
        return ConceptCandidate(
            seed_id=f"seed-forge-{wildness_level.lower()}-{invented}-{mechanism}",
            source_kind="random_grammar",
            source_ref=None,
            concept_text=(
                f"Assume {invented} {mechanism} coupling that shifts the sound horizon "
                "while preserving late local calibration observables"
            ),
            wildness_level=wildness_level,
            seed=self.seed,
            operators=("random_grammar", "assumption_addition"),
            parameter_budget=5,
            assumption_diff=AssumptionDiff(
                kept=["observed_redshift_distance_relation"],
                added=[f"{invented}_{mechanism}_coupling"],
                modified=["time_evolution"],
            ),
            falsification_tests=_default_falsification_tests(),
            reason_for_queue_entry="seeded random start for speculative discovery search",
        )


class PriorArtChecker:
    def __init__(self, corpus: Mapping[str, Any]) -> None:
        self.corpus = corpus

    def check(self, candidate: ConceptCandidate) -> dict[str, Any]:
        similarity = max(
            (
                _jaccard(candidate.concept_text, str(paper.get("title", "")))
                for paper in _paper_items(self.corpus)
            ),
            default=0.0,
        )
        required = candidate.wildness_level in {"W3", "W4", "W5"}
        verdict = "checked_local_corpus" if required else "not_required_for_wildness"
        if similarity > 0.85:
            verdict = "duplicate_or_near_duplicate"
        return {
            "max_local_similarity": round(similarity, 4),
            "requires_prior_art": required,
            "searched_sources": ["local_corpus"],
            "verdict": verdict,
            "web_status": "available_when_configured",
        }


class DuplicateDetector:
    def is_duplicate(self, concept_text: str, existing_texts: Sequence[str]) -> bool:
        return any(_jaccard(concept_text, item) > 0.85 for item in existing_texts)


@dataclass(frozen=True)
class FictionSource:
    source_id: str
    title: str
    license_kind: str
    text: str
    status: str = "active"
    consecutive_failed_ab_cycles: int = 0

    @property
    def allowed(self) -> bool:
        return self.license_kind in {"public_domain", "cc", "project_owned", "user_authored"}


class SciFiMotifMiner:
    def mine(self, source: FictionSource) -> tuple[ConceptCandidate, ...]:
        if not source.allowed or source.status != "active":
            return ()
        digest = hashlib.sha256(source.text.encode("utf-8")).hexdigest()[:8]
        return (
            ConceptCandidate(
                seed_id=f"seed-fiction-{source.source_id}-{digest}",
                source_kind="fiction_motif",
                source_ref=source.source_id,
                concept_text=(
                    "Assume a story-inspired hidden boundary motif as inspiration only, "
                    "then require ordinary dataset falsification"
                ),
                wildness_level="W4",
                seed=int(digest[:6], 16),
                operators=("motif_ablation", "assumption_addition"),
                parameter_budget=5,
                assumption_diff=AssumptionDiff(
                    kept=["dataset_falsification"],
                    added=["hidden_boundary_motif"],
                ),
                falsification_tests=_default_falsification_tests(),
                reason_for_queue_entry="allowlisted fiction motif used only as inspiration",
                fiction_inspiration_only=True,
            ),
        )


def motif_closure_status(source: FictionSource) -> dict[str, Any]:
    failed = source.consecutive_failed_ab_cycles >= 3
    return {
        "config_migration_required_to_reenable": failed,
        "new_status": "disabled_permanent" if failed else source.status,
        "reason": "three_failed_motif_ab_cycles" if failed else "active_or_observing",
    }


def _default_falsification_tests() -> tuple[str, ...]:
    return (
        "L0 schema and assumption-diff validity",
        "L1 generated formula parseability",
        "L2 summary-likelihood sanity across CMB, BAO, SN, BBN, S8, and local H0",
    )


def _paper_items(corpus: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    papers = corpus.get("papers", ())
    if isinstance(papers, list):
        return tuple(item for item in papers if isinstance(item, Mapping))
    return ()


def _paper_id(paper: Mapping[str, Any]) -> str | None:
    value = paper.get("paper_id")
    return value if isinstance(value, str) else None


def _title_from_concept(text: str) -> str:
    cleaned = text.removeprefix("Assume ").rstrip(".")
    return cleaned[:1].upper() + cleaned[1:]


def _jaccard(a: str, b: str) -> float:
    left = set(a.lower().split())
    right = set(b.lower().split())
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)
