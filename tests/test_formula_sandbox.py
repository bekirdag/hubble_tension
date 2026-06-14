from __future__ import annotations

from pathlib import Path

from hubble_tension.equations import EquationBuilder, MathCritic
from hubble_tension.generated_models import GeneratedModelRenderer
from hubble_tension.runners import SandboxRunner, static_isolation_diagnostics
from hubble_tension.state import ArtifactProvenance


def test_equation_builder_and_math_critic_accept_stub_model() -> None:
    equations = EquationBuilder().build({"concept_name": "zoroto", "wildness_level": "W3"})
    critique = MathCritic().review(equations)

    assert equations["family_label"] == "unchecked_or_phenomenological"
    assert critique["diagnostics"] == []
    assert critique["parseable"] is True


def test_math_critic_flags_bad_formula() -> None:
    critique = MathCritic().review(
        {
            "parameters": {"alpha": {"min": 1.0, "max": 0.0}},
            "sympy_expressions": {"bad": "alpha + missing + "},
            "variables": ["alpha"],
        }
    )

    assert "bad:parse_error" in critique["diagnostics"]
    assert "alpha:bounds_invalid" in critique["diagnostics"]


def test_generated_module_static_sandbox_checks(tmp_path: Path) -> None:
    rendered = GeneratedModelRenderer().write_module(
        output_dir=tmp_path,
        module_name="stub_model",
        equations=EquationBuilder().build({"concept_name": "zoroto"}),
        provenance=ArtifactProvenance(
            agent_id="stub",
            agent_version_hash="agent-hash",
            prompt_template_id="lab_head",
            prompt_template_hash="prompt-hash",
        ),
    )

    result = SandboxRunner(runtime_name="definitely-missing-runtime").run_static_checks(
        rendered.path
    )

    assert result.status == "passed_static_sandbox_checks"
    assert result.startup_log["runtime_status"] == "sandbox_unavailable"
    assert static_isolation_diagnostics("import socket\nopen('x', 'w')\n") == [
        "forbidden_import:socket",
        "forbidden_call:open",
    ]
