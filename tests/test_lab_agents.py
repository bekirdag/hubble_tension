from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from hubble_tension.lab import select_lab_head
from hubble_tension.runtime.config import read_lab_head_config


def test_stub_lab_head_selection_has_provenance() -> None:
    config = read_lab_head_config(Path("config/lab_head.yaml"), {"HT_LAB_HEAD_AGENT": "stub"})

    selection = select_lab_head(config=config, prompt_dir=Path("prompts"), env={})

    assert selection.available is True
    assert selection.agent_id == "stub"
    assert len(selection.agent_version_hash) == 64
    assert selection.provenance.prompt_template_id == "lab_head"


def test_fallback_uses_only_healthy_local_agents() -> None:
    inventory = {
        "agents": [
            {"id": "remote-agent", "health_status": "healthy", "cloud": True},
            {"id": "local-agent", "health_status": "healthy", "adapter": "ollama"},
        ]
    }
    config = read_lab_head_config(Path("config/lab_head.yaml"), {})

    selection = select_lab_head(
        config=config,
        prompt_dir=Path("prompts"),
        env={"HT_LAB_AGENT_INVENTORY_JSON": json.dumps(inventory)},
    )

    assert selection.available is True
    assert selection.agent_id == "local-agent"
    assert selection.fallback_used is True


def test_unavailable_agent_records_configured_status_without_prompt() -> None:
    config = read_lab_head_config(Path("config/lab_head.yaml"), {})

    selection = select_lab_head(
        config=config,
        prompt_dir=Path("prompts"),
        env={"HT_LAB_AGENT_INVENTORY_JSON": "[]"},
    )

    assert selection.available is False
    assert selection.status == "lab_head_unavailable"
    assert selection.fallback_used is False


def test_mcoda_selection_checks_requested_agent_details_first(monkeypatch: Any) -> None:
    config = read_lab_head_config(Path("config/lab_head.yaml"), {})
    calls: list[tuple[str, ...]] = []

    def fake_run(
        command: Sequence[str],
        **_: object,
    ) -> SimpleNamespace:
        command_tuple = tuple(command)
        calls.append(command_tuple)
        assert command_tuple == ("mcoda", "agent", "details", "codex55", "--json")
        return SimpleNamespace(
            stdout=json.dumps(
                {
                    "slug": "codex55",
                    "health": {"status": "healthy"},
                    "adapter": "codex-cli",
                    "execution": "local",
                }
            )
        )

    monkeypatch.setattr(
        "hubble_tension.lab.agents.shutil.which",
        lambda _: "/opt/homebrew/bin/mcoda",
    )
    monkeypatch.setattr("hubble_tension.lab.agents.subprocess.run", fake_run)

    selection = select_lab_head(config=config, prompt_dir=Path("prompts"), env={})

    assert selection.available is True
    assert selection.agent_id == "codex55"
    assert selection.reason == "configured_agent_available"
    assert calls == [("mcoda", "agent", "details", "codex55", "--json")]
