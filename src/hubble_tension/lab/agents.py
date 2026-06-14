from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from hubble_tension.state import ArtifactProvenance, prompt_template_hash

STUB_AGENT_ID = "stub"


class _FallbackConfigLike(Protocol):
    @property
    def allow_healthy_local_agents(self) -> bool:
        ...

    @property
    def unavailable_status(self) -> str:
        ...


class _LabHeadConfigLike(Protocol):
    @property
    def adapter(self) -> str:
        ...

    @property
    def agent(self) -> str:
        ...

    @property
    def execution(self) -> str:
        ...

    @property
    def fallback(self) -> _FallbackConfigLike:
        ...


@dataclass(frozen=True)
class LabHeadSelection:
    agent_id: str
    agent_version_hash: str
    adapter: str
    execution: str
    status: str
    available: bool
    fallback_used: bool
    reason: str
    prompt_template_id: str
    prompt_template_hash: str

    @property
    def provenance(self) -> ArtifactProvenance:
        return ArtifactProvenance(
            agent_id=self.agent_id,
            agent_version_hash=self.agent_version_hash,
            prompt_template_id=self.prompt_template_id,
            prompt_template_hash=self.prompt_template_hash,
        )

    def as_state(self) -> dict[str, str | bool]:
        return {
            "adapter": self.adapter,
            "agent_id": self.agent_id,
            "agent_version_hash": self.agent_version_hash,
            "available": self.available,
            "execution": self.execution,
            "fallback_used": self.fallback_used,
            "prompt_template_hash": self.prompt_template_hash,
            "prompt_template_id": self.prompt_template_id,
            "reason": self.reason,
            "status": self.status,
        }


def select_lab_head(
    *,
    config: _LabHeadConfigLike,
    prompt_dir: Path,
    env: Mapping[str, str],
) -> LabHeadSelection:
    """Select the configured lab-head agent without any human prompt fallback."""

    template_hash = prompt_template_hash(prompt_dir, "lab_head")
    requested_agent = env.get("HT_LAB_HEAD_AGENT") or config.agent
    if requested_agent == STUB_AGENT_ID:
        return LabHeadSelection(
            agent_id=STUB_AGENT_ID,
            agent_version_hash=_stable_hash({"agent": STUB_AGENT_ID, "fixture": "phase5"}),
            adapter="fixture",
            execution="local_only",
            status="available",
            available=True,
            fallback_used=False,
            reason="stub_lab_head_requested",
            prompt_template_id="lab_head",
            prompt_template_hash=template_hash,
        )

    inventory = _load_agent_inventory(
        config=config,
        env=env,
        requested_agent=requested_agent,
    )
    requested = _find_agent(inventory, requested_agent)
    if requested is not None and _is_healthy_local(requested):
        return _selection_from_agent(
            requested,
            config=config,
            template_hash=template_hash,
            fallback_used=False,
            reason="configured_agent_available",
        )

    if config.fallback.allow_healthy_local_agents:
        fallback = next((item for item in inventory if _is_healthy_local(item)), None)
        if fallback is not None:
            return _selection_from_agent(
                fallback,
                config=config,
                template_hash=template_hash,
                fallback_used=True,
                reason=f"configured_agent_unavailable:{requested_agent}",
            )

    return LabHeadSelection(
        agent_id=requested_agent,
        agent_version_hash=_stable_hash(
            {
                "adapter": config.adapter,
                "agent": requested_agent,
                "status": config.fallback.unavailable_status,
            }
        ),
        adapter=config.adapter,
        execution=config.execution,
        status=config.fallback.unavailable_status,
        available=False,
        fallback_used=False,
        reason="configured_agent_unavailable",
        prompt_template_id="lab_head",
        prompt_template_hash=template_hash,
    )


def _selection_from_agent(
    agent: Mapping[str, Any],
    *,
    config: _LabHeadConfigLike,
    template_hash: str,
    fallback_used: bool,
    reason: str,
) -> LabHeadSelection:
    agent_id = _agent_id(agent)
    return LabHeadSelection(
        agent_id=agent_id,
        agent_version_hash=_agent_version_hash(agent),
        adapter=str(agent.get("adapter") or agent.get("adapter_type") or config.adapter),
        execution="local_only",
        status="available",
        available=True,
        fallback_used=fallback_used,
        reason=reason,
        prompt_template_id="lab_head",
        prompt_template_hash=template_hash,
    )


def _load_agent_inventory(
    *,
    config: _LabHeadConfigLike,
    env: Mapping[str, str],
    requested_agent: str,
) -> tuple[Mapping[str, Any], ...]:
    fixture = env.get("HT_LAB_AGENT_INVENTORY_JSON")
    if fixture:
        payload = json.loads(fixture)
        return tuple(_inventory_items(payload))

    if config.adapter != "mcoda" or shutil.which("mcoda") is None:
        return ()

    requested_details = _load_mcoda_agent_details(requested_agent, env)
    if requested_details is not None:
        return (requested_details,)

    for command in (
        ("mcoda", "agent", "list", "--json", "--no-refresh-health"),
        ("mcoda", "agent", "list", "--json", "--refresh-health"),
        ("mcoda", "agent", "list", "--json"),
    ):
        try:
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=_mcoda_timeout_seconds(env),
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            continue
        payload = json.loads(result.stdout)
        return tuple(_inventory_items(payload))
    return ()


def _load_mcoda_agent_details(
    requested_agent: str,
    env: Mapping[str, str],
) -> Mapping[str, Any] | None:
    try:
        result = subprocess.run(
            ("mcoda", "agent", "details", requested_agent, "--json"),
            check=True,
            capture_output=True,
            text=True,
            timeout=_mcoda_timeout_seconds(env),
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    payload = json.loads(result.stdout)
    return payload if isinstance(payload, Mapping) else None


def _mcoda_timeout_seconds(env: Mapping[str, str]) -> float:
    configured = env.get("HT_LAB_MCODA_TIMEOUT_SECONDS")
    if configured is None:
        return 15.0
    try:
        return max(1.0, float(configured))
    except ValueError:
        return 15.0


def _inventory_items(payload: object) -> Sequence[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("agents", "items", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, Mapping)]
    return ()


def _find_agent(
    inventory: Sequence[Mapping[str, Any]],
    requested_agent: str,
) -> Mapping[str, Any] | None:
    for item in inventory:
        if requested_agent in {
            str(item.get("id", "")),
            str(item.get("agent_id", "")),
            str(item.get("slug", "")),
            str(item.get("agent_slug", "")),
            str(item.get("name", "")),
        }:
            return item
    return None


def _is_healthy_local(agent: Mapping[str, Any]) -> bool:
    health = _health_status(agent)
    if health not in {"healthy", "ok", "available", ""}:
        return False
    if bool(agent.get("remote")) or bool(agent.get("cloud")):
        return False
    agent_id = _agent_id(agent).lower()
    adapter = str(agent.get("adapter") or agent.get("adapter_type") or "").lower()
    execution = str(agent.get("execution") or agent.get("scope") or "local").lower()
    if agent_id.startswith("mswarm-cloud-"):
        return False
    return "cloud" not in adapter and "remote" not in execution


def _health_status(agent: Mapping[str, Any]) -> str:
    raw_health = agent.get("health_status") or agent.get("health") or ""
    if isinstance(raw_health, Mapping):
        raw_health = raw_health.get("status", "")
    return str(raw_health).lower()


def _agent_id(agent: Mapping[str, Any]) -> str:
    for key in ("agent_id", "id", "agent_slug", "slug", "name"):
        value = agent.get(key)
        if isinstance(value, str) and value:
            return value
    return "unknown-local-agent"


def _agent_version_hash(agent: Mapping[str, Any]) -> str:
    explicit = agent.get("agent_version_hash") or agent.get("version_hash")
    if isinstance(explicit, str) and explicit:
        return explicit
    return _stable_hash(dict(sorted((str(key), value) for key, value in agent.items())))


def _stable_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
