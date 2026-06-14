from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LockCollision:
    run_id: str
    state_path: str
    log_path: str
    pid: int | None


class FileLock:
    """Small exclusive file lock with stale-pid cleanup."""

    def __init__(self, path: Path, payload: Mapping[str, Any]) -> None:
        self.path = path
        self.payload = dict(payload)
        self._acquired = False

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError as exc:
                existing = _load_lock(self.path)
                pid = _pid(existing)
                if pid is not None and _pid_is_alive(pid):
                    raise LockCollisionError(
                        LockCollision(
                            run_id=str(existing.get("run_id", "unknown")),
                            state_path=str(existing.get("state_path", "unknown")),
                            log_path=str(existing.get("log_path", "unknown")),
                            pid=pid,
                        )
                    ) from exc
                self.path.unlink(missing_ok=True)
                continue

            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self.payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
            self._acquired = True
            return

    def release(self) -> None:
        if not self._acquired:
            return
        self.path.unlink(missing_ok=True)
        self._acquired = False

    def __enter__(self) -> FileLock:
        self.acquire()
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.release()


class LockCollisionError(RuntimeError):
    def __init__(self, collision: LockCollision) -> None:
        super().__init__("runtime lock is held by an active process")
        self.collision = collision


def _load_lock(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _pid(payload: Mapping[str, Any]) -> int | None:
    value = payload.get("pid")
    if isinstance(value, int):
        return value
    return None


def _pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
