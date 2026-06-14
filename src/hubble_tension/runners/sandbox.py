from __future__ import annotations

import ast
import shutil
from dataclasses import dataclass
from pathlib import Path

FORBIDDEN_IMPORTS = {"os", "socket", "subprocess", "requests", "urllib", "pathlib"}
FORBIDDEN_CALLS = {"open", "exec", "eval", "__import__"}


@dataclass(frozen=True)
class SandboxResult:
    status: str
    diagnostics: tuple[str, ...]
    startup_log: dict[str, str | int | bool]


class SandboxRunner:
    """Static and runtime-selection sandbox facade for generated modules."""

    def __init__(
        self,
        *,
        runtime_name: str = "podman",
        cpu_limit: int = 1,
        memory_mb: int = 512,
    ) -> None:
        self.runtime_name = runtime_name
        self.cpu_limit = cpu_limit
        self.memory_mb = memory_mb

    def runtime_status(self) -> str:
        return "available" if shutil.which(self.runtime_name) else "sandbox_unavailable"

    def startup_log(self) -> dict[str, str | int | bool]:
        return {
            "cpu_limit": self.cpu_limit,
            "license_note": "runtime_license_must_be_verified_by_operator_environment",
            "memory_mb": self.memory_mb,
            "mount_mode": "read_only",
            "network": False,
            "runtime_name": self.runtime_name,
            "runtime_status": self.runtime_status(),
        }

    def run_static_checks(self, path: Path) -> SandboxResult:
        diagnostics = tuple(static_isolation_diagnostics(path.read_text(encoding="utf-8")))
        return SandboxResult(
            status="passed_static_sandbox_checks" if not diagnostics else "failed_static_sandbox",
            diagnostics=diagnostics,
            startup_log=self.startup_log(),
        )


def static_isolation_diagnostics(code: str) -> list[str]:
    diagnostics: list[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"syntax_error:{exc.lineno}"]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".", 1)[0] in FORBIDDEN_IMPORTS:
                    diagnostics.append(f"forbidden_import:{alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".", 1)[0] in FORBIDDEN_IMPORTS:
                diagnostics.append(f"forbidden_import:{node.module}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in FORBIDDEN_CALLS:
                diagnostics.append(f"forbidden_call:{node.func.id}")
    return diagnostics
