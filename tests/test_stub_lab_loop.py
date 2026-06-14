from __future__ import annotations

import json
import sqlite3
from io import StringIO
from pathlib import Path

from hubble_tension.runtime import RuntimeSupervisor


def test_stub_lab_loop_launcher_cycle_persists_all_phase5_records(tmp_path: Path) -> None:
    output = StringIO()
    result = RuntimeSupervisor(
        state_dir=tmp_path,
        env={
            "HT_LAB_CORPUS_SOURCE": "mock",
            "HT_LAB_DRY_RUN": "1",
            "HT_LAB_ENABLE_PHASE5_LOOP": "1",
            "HT_LAB_HEAD_AGENT": "stub",
        },
        stream=output,
    ).run()
    state = json.loads((tmp_path / "runtime_state.json").read_text(encoding="utf-8"))

    assert result.status == "ready"
    assert state["active_hypothesis_id"] == "hyp-stub-zoroto-000001"
    assert state["last_lab_head_decision_id"] == "decision-stub-zoroto-000001"
    assert state["lab_loop"]["stage_history"] == [
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
    ]
    assert "stage=phase5" in output.getvalue()
    assert (tmp_path / "runs" / "run-000001" / "generated_models" / "stub_zoroto_model.py").exists()

    with sqlite3.connect(tmp_path / "lab_state.sqlite3") as connection:
        counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "concept_seeds",
                "hypotheses",
                "formal_models",
                "implementations",
                "metric_packets",
                "lab_notes",
                "lab_head_decisions",
                "generator_health",
            )
        }
        decision = connection.execute(
            """
            SELECT agent_id, agent_version_hash, prompt_template_hash, rationale, uncertainty
            FROM lab_head_decisions
            WHERE decision_id = 'decision-stub-zoroto-000001'
            """
        ).fetchone()
    assert all(value == 1 for value in counts.values())
    assert decision[0] == "stub"
    assert len(decision[1]) == 64
    assert len(decision[2]) == 64
    assert decision[3]
    assert decision[4] == "medium"


def test_phase5_loop_records_unavailable_lab_head_bootstrap(tmp_path: Path) -> None:
    result = RuntimeSupervisor(
        state_dir=tmp_path,
        env={
            "HT_LAB_AGENT_INVENTORY_JSON": "[]",
            "HT_LAB_DRY_RUN": "1",
            "HT_LAB_ENABLE_PHASE5_LOOP": "1",
        },
        stream=StringIO(),
    ).run()
    state = json.loads((tmp_path / "runtime_state.json").read_text(encoding="utf-8"))

    assert result.status == "lab_head_unavailable"
    assert state["bootstrap_blocker"] == "lab_head_unavailable"
    assert state["lab_head"]["available"] is False
