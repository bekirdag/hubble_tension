from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

BOOTSTRAP_SOLVER_UNAVAILABLE = "bootstrap_solver_unavailable"
INTEGRATION_PENDING = "integration_pending"
SOLVER_AVAILABLE = "available"


@dataclass(frozen=True)
class SolverSource:
    name: str
    family: str
    repo_url: str
    pinned_ref_kind: str
    pinned_ref: str
    pinned_ref_verified_at: str
    required_ref_env: str
    required_for_probe: bool


@dataclass(frozen=True)
class SolverEnvironmentConfig:
    image: str
    runtime: str
    install_prefix: str
    compiler: str
    openmp: str
    blas: str
    python_bindings: bool
    default_sampler: str
    fallback_sampler: str
    l7_attempt_hours: int
    l7_total_candidate_hours: int
    timeout_status: str
    missing_likelihood_status: str
    sources: tuple[SolverSource, ...]

    @property
    def required_sources(self) -> tuple[SolverSource, ...]:
        return tuple(source for source in self.sources if source.required_for_probe)


@dataclass(frozen=True)
class SolverProbeResult:
    status: str
    reason: str
    install_prefix: str
    available_sources: tuple[str, ...]
    missing_sources: tuple[str, ...]
    required_ref_envs: tuple[str, ...]
    source_pins: dict[str, str]

    def as_state(self) -> dict[str, object]:
        return {
            "available_sources": list(self.available_sources),
            "install_prefix": self.install_prefix,
            "missing_sources": list(self.missing_sources),
            "reason": self.reason,
            "required_ref_envs": list(self.required_ref_envs),
            "source_pins": dict(sorted(self.source_pins.items())),
            "status": self.status,
        }


def read_solver_config(path: Path) -> SolverEnvironmentConfig:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Solver config must be a mapping: {path}")

    container = _mapping(payload, "container")
    toolchain = _mapping(payload, "toolchain")
    posterior = _mapping(payload, "posterior")
    sources_payload = _mapping(payload, "sources")
    sources: list[SolverSource] = []
    for source_name, source_payload in sorted(sources_payload.items()):
        if not isinstance(source_name, str) or not isinstance(source_payload, Mapping):
            raise ValueError(f"Solver source must be a mapping: {source_name}")
        sources.append(
            SolverSource(
                name=source_name,
                family=_str(source_payload, "family"),
                repo_url=_str(source_payload, "repo_url"),
                pinned_ref_kind=_str(source_payload, "pinned_ref_kind"),
                pinned_ref=_str(source_payload, "pinned_ref"),
                pinned_ref_verified_at=_str(source_payload, "pinned_ref_verified_at"),
                required_ref_env=_str(source_payload, "required_ref_env"),
                required_for_probe=_bool(source_payload, "required_for_probe"),
            )
        )

    return SolverEnvironmentConfig(
        image=_str(container, "image"),
        runtime=_str(container, "runtime"),
        install_prefix=_str(container, "install_prefix"),
        compiler=_str(toolchain, "compiler"),
        openmp=_str(toolchain, "openmp"),
        blas=_str(toolchain, "blas"),
        python_bindings=_bool(toolchain, "python_bindings"),
        default_sampler=_str(posterior, "default_sampler"),
        fallback_sampler=_str(posterior, "fallback_sampler"),
        l7_attempt_hours=_int(posterior, "l7_attempt_hours"),
        l7_total_candidate_hours=_int(posterior, "l7_total_candidate_hours"),
        timeout_status=_str(posterior, "timeout_status"),
        missing_likelihood_status=_str(posterior, "missing_likelihood_status"),
        sources=tuple(sources),
    )


def solver_package_status(
    *,
    repo_root: Path,
    env: Mapping[str, str],
) -> SolverProbeResult:
    config = read_solver_config(repo_root / "config" / "solvers.yaml")
    if env.get("HT_LAB_ENABLE_SOLVER_PROBE") != "1" and env.get("HT_LAB_REQUIRE_SOLVERS") != "1":
        return SolverProbeResult(
            status=INTEGRATION_PENDING,
            reason="solver probe not requested",
            install_prefix=_install_prefix(repo_root, config, env),
            available_sources=(),
            missing_sources=(),
            required_ref_envs=tuple(source.required_ref_env for source in config.required_sources),
            source_pins=_source_pins(config),
        )
    return probe_solver_environment(config=config, repo_root=repo_root, env=env)


def probe_solver_environment(
    *,
    config: SolverEnvironmentConfig,
    repo_root: Path,
    env: Mapping[str, str],
) -> SolverProbeResult:
    install_prefix = _install_prefix(repo_root, config, env)
    required_ref_envs = tuple(source.required_ref_env for source in config.required_sources)
    if env.get("HT_LAB_FAKE_SOLVER_PROBE_FAIL") == "1":
        return SolverProbeResult(
            status=BOOTSTRAP_SOLVER_UNAVAILABLE,
            reason="forced solver probe failure",
            install_prefix=install_prefix,
            available_sources=(),
            missing_sources=tuple(source.name for source in config.required_sources),
            required_ref_envs=required_ref_envs,
            source_pins=_source_pins(config),
        )

    available: list[str] = []
    missing: list[str] = []
    for source in config.required_sources:
        source_path = Path(install_prefix) / "src" / source.name
        if source_path.exists():
            available.append(source.name)
        else:
            missing.append(source.name)

    status = SOLVER_AVAILABLE if not missing else BOOTSTRAP_SOLVER_UNAVAILABLE
    reason = (
        "required solver sources are present"
        if not missing
        else "required solver sources missing"
    )
    return SolverProbeResult(
        status=status,
        reason=reason,
        install_prefix=install_prefix,
        available_sources=tuple(available),
        missing_sources=tuple(missing),
        required_ref_envs=required_ref_envs,
        source_pins=_source_pins(config),
    )


def _install_prefix(
    repo_root: Path,
    config: SolverEnvironmentConfig,
    env: Mapping[str, str],
) -> str:
    configured = env.get("HT_SOLVER_PREFIX") or config.install_prefix
    path = Path(configured)
    return str(path if path.is_absolute() else repo_root / path)


def _source_pins(config: SolverEnvironmentConfig) -> dict[str, str]:
    return {source.name: source.pinned_ref for source in config.sources}


def _mapping(payload: Mapping[object, object], key: str) -> Mapping[object, object]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"Solver config section must be a mapping: {key}")
    return value


def _str(payload: Mapping[object, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Solver config value must be a non-empty string: {key}")
    return value


def _int(payload: Mapping[object, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int):
        raise ValueError(f"Solver config value must be an integer: {key}")
    return value


def _bool(payload: Mapping[object, object], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"Solver config value must be a boolean: {key}")
    return value
