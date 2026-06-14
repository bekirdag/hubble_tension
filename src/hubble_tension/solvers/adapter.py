from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from hubble_tension.schemas.candidates import CandidateRecord

SUPPORTED_MODEL_FAMILIES = {
    "lambda_cdm": ("class",),
    "stock_extension": ("class",),
    "early_dark_energy": ("class", "class_ede"),
    "ede": ("class", "class_ede"),
    "axion_like_early_universe": ("class", "axiclass"),
    "axi_ede": ("class", "axiclass"),
    "recombination_history": ("class", "hyrec2"),
}


@dataclass(frozen=True)
class SolverRequest:
    candidate_id: str
    hypothesis_id: str
    model_family: str
    solver_backend: str | None
    status: str
    required_sources: tuple[str, ...]
    parameters: dict[str, Any]
    reason: str


class CandidateSolverAdapter:
    def adapt(
        self,
        candidate: CandidateRecord,
        *,
        model_family: str,
        parameters: Mapping[str, Any] | None = None,
    ) -> SolverRequest:
        normalized_family = model_family.strip().lower()
        provided_parameters = dict(
            parameters or candidate.metrics_json.get("solver_parameters", {})
        )
        if (
            candidate.wildness_level in {"W4", "W5"}
            and normalized_family not in SUPPORTED_MODEL_FAMILIES
        ):
            return SolverRequest(
                candidate_id=candidate.candidate_id,
                hypothesis_id=candidate.hypothesis_id,
                model_family=normalized_family,
                solver_backend=None,
                status="phenomenological_background",
                required_sources=(),
                parameters=provided_parameters,
                reason="unsupported W4-W5 idea remains phenomenological_background",
            )
        required_sources = SUPPORTED_MODEL_FAMILIES.get(normalized_family)
        if required_sources is None:
            return SolverRequest(
                candidate_id=candidate.candidate_id,
                hypothesis_id=candidate.hypothesis_id,
                model_family=normalized_family,
                solver_backend=None,
                status="unsupported_model_family",
                required_sources=(),
                parameters=provided_parameters,
                reason="model family has no supported Phase 10 solver adapter",
            )

        return SolverRequest(
            candidate_id=candidate.candidate_id,
            hypothesis_id=candidate.hypothesis_id,
            model_family=normalized_family,
            solver_backend=required_sources[-1],
            status="solver_request_ready",
            required_sources=required_sources,
            parameters=provided_parameters,
            reason="candidate mapped to supported Phase 10 solver family",
        )
