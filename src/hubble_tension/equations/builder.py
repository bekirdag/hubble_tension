from __future__ import annotations

import ast
from collections.abc import Mapping
from typing import Any


class EquationBuilder:
    """Build SymPy-compatible formula payloads from hypothesis records."""

    def build(self, hypothesis_json: Mapping[str, Any]) -> dict[str, Any]:
        wildness = str(hypothesis_json.get("wildness_level", "W0"))
        concept_name = str(hypothesis_json.get("concept_name", "generated_concept"))
        return {
            "concept_name": concept_name,
            "family_label": (
                "supported_summary_screen"
                if wildness in {"W0", "W1", "W2"}
                else "unchecked_or_phenomenological"
            ),
            "parameters": {
                "H0_lcdm": {"min": 50.0, "max": 90.0, "units": "km/s/Mpc"},
                "alpha_zoroto": {"min": 0.0, "max": 1.0, "units": "dimensionless"},
                "z_transition": {"min": 500.0, "max": 5000.0, "units": "redshift"},
            },
            "sympy_expressions": {
                "h0_effective": "H0_lcdm + alpha_zoroto * exp(-z / z_transition)",
                "rs_drag_shift": "-0.08 * alpha_zoroto",
                "s8_shift": "0.02 * alpha_zoroto",
            },
            "variables": ["H0_lcdm", "alpha_zoroto", "z_transition", "z"],
        }


class MathCritic:
    """Static critic for generated equation payloads before stronger math engines exist."""

    def review(self, equations: Mapping[str, Any]) -> dict[str, Any]:
        diagnostics: list[str] = []
        expressions = equations.get("sympy_expressions", {})
        raw_variables = equations.get("variables", [])
        variables = set(raw_variables) if isinstance(raw_variables, list) else set()
        if not isinstance(expressions, Mapping):
            diagnostics.append("expressions_not_mapping")
            expressions = {}
        for name, expression in expressions.items():
            if not isinstance(expression, str):
                diagnostics.append(f"{name}:expression_not_string")
                continue
            diagnostics.extend(_expression_diagnostics(str(name), expression, variables))
        diagnostics.extend(_parameter_diagnostics(equations.get("parameters", {})))
        label = "passed_static_math_critic" if not diagnostics else "failed_static_math_critic"
        return {
            "diagnostics": diagnostics,
            "label": label,
            "parseable": not any("parse" in diagnostic for diagnostic in diagnostics),
        }


def _expression_diagnostics(name: str, expression: str, variables: set[object]) -> list[str]:
    diagnostics: list[str] = []
    if expression.count("(") != expression.count(")"):
        diagnostics.append(f"{name}:unbalanced_parentheses")
    if "/ 0" in expression or "/0" in expression:
        diagnostics.append(f"{name}:literal_zero_division")
    python_expression = expression.replace("exp", "math_exp")
    try:
        parsed = ast.parse(python_expression, mode="eval")
    except SyntaxError:
        diagnostics.append(f"{name}:parse_error")
        return diagnostics
    names = {node.id for node in ast.walk(parsed) if isinstance(node, ast.Name)}
    unresolved = names - variables - {"math_exp"}
    if unresolved:
        diagnostics.append(f"{name}:unresolved_variables:{','.join(sorted(unresolved))}")
    return diagnostics


def _parameter_diagnostics(parameters: object) -> list[str]:
    if not isinstance(parameters, Mapping):
        return ["parameters_not_mapping"]
    diagnostics: list[str] = []
    for name, bounds in parameters.items():
        if not isinstance(bounds, Mapping):
            diagnostics.append(f"{name}:bounds_not_mapping")
            continue
        lower = bounds.get("min")
        upper = bounds.get("max")
        if not isinstance(lower, int | float) or not isinstance(upper, int | float):
            diagnostics.append(f"{name}:bounds_missing")
        elif lower >= upper:
            diagnostics.append(f"{name}:bounds_invalid")
    return diagnostics
