from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

JsonObject = dict[str, Any]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class RuntimeStore:
    """File-backed Phase 1 state, event, and checkpoint store."""

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir
        self.state_path = state_dir / "runtime_state.json"
        self.lock_path = state_dir / "lock.json"
        self.events_path = state_dir / "events.jsonl"
        self.checkpoint_dir = state_dir / "checkpoints"
        self.runs_dir = state_dir / "runs"
        self.stable_candidate_path = state_dir / "stable_candidate.json"

    def ensure(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def run_dir_for(self, run_id: str) -> Path:
        return self.runs_dir / run_id

    def log_path_for(self, run_id: str) -> Path:
        return self.run_dir_for(run_id) / "lab.log"

    def stop_path_for(self, run_id: str) -> Path:
        return self.run_dir_for(run_id) / "STOP"

    def load_state(self) -> JsonObject | None:
        if not self.state_path.exists():
            return None
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Runtime state must be a JSON object: {self.state_path}")
        return payload

    def save_state(self, state: Mapping[str, Any]) -> None:
        _atomic_write_json(self.state_path, state)

    def append_event(self, event: Mapping[str, Any]) -> None:
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(dict(event), sort_keys=True) + "\n")

    def write_checkpoint(self, state: Mapping[str, Any], reason: str) -> Path:
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_count = int(state.get("checkpoint_count", 0))
        checkpoint_path = self.checkpoint_dir / f"checkpoint-{checkpoint_count:06d}.json"
        payload = {
            "reason": reason,
            "recorded_at": utc_now(),
            "state": dict(state),
        }
        _atomic_write_json(checkpoint_path, payload)
        _atomic_write_json(self.checkpoint_dir / "latest.json", payload)
        return checkpoint_path

    def load_stable_candidate(self) -> JsonObject | None:
        if not self.stable_candidate_path.exists():
            return None
        payload = json.loads(self.stable_candidate_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(
                f"Stable candidate record must be a JSON object: {self.stable_candidate_path}"
            )
        return payload


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)
