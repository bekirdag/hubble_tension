from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hubble_tension.state import ArtifactProvenance


@dataclass(frozen=True)
class RenderedModel:
    path: Path
    code_hash: str


class GeneratedModelRenderer:
    """Render harmless generated model modules under controlled run paths."""

    def write_module(
        self,
        *,
        output_dir: Path,
        module_name: str,
        equations: Mapping[str, Any],
        provenance: ArtifactProvenance,
    ) -> RenderedModel:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{module_name}.py"
        code = self.render(equations=equations, provenance=provenance)
        path.write_text(code, encoding="utf-8")
        return RenderedModel(
            path=path,
            code_hash=hashlib.sha256(code.encode("utf-8")).hexdigest(),
        )

    def render(
        self,
        *,
        equations: Mapping[str, Any],
        provenance: ArtifactProvenance,
    ) -> str:
        concept_name = str(equations.get("concept_name", "generated_concept"))
        return f'''"""Generated model module for {concept_name}.

agent_id = {provenance.agent_id!r}
agent_version_hash = {provenance.agent_version_hash!r}
prompt_template_hash = {provenance.prompt_template_hash!r}
"""

from __future__ import annotations

import math


PROVENANCE = {{
    "agent_id": {provenance.agent_id!r},
    "agent_version_hash": {provenance.agent_version_hash!r},
    "prompt_template_id": {provenance.prompt_template_id!r},
    "prompt_template_hash": {provenance.prompt_template_hash!r},
}}


def evaluate(params: dict[str, float], observables: dict[str, float]) -> dict[str, float]:
    h0_lcdm = params.get("H0_lcdm", 67.4)
    alpha_zoroto = params.get("alpha_zoroto", 0.0)
    z_transition = max(params.get("z_transition", 3000.0), 1.0)
    z_value = observables.get("z", 1100.0)
    h0_effective = h0_lcdm + alpha_zoroto * math.exp(-z_value / z_transition)
    return {{
        "h0_effective": h0_effective,
        "rs_drag_shift": -0.08 * alpha_zoroto,
        "s8_shift": 0.02 * alpha_zoroto,
    }}
'''
