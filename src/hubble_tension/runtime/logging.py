from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO


@dataclass(frozen=True)
class LogContext:
    attempt_id: str
    branch_id: str
    test_id: str


class LabLogger:
    """Stream runtime log lines to stdout and the active run log."""

    def __init__(self, log_path: Path, stream: TextIO | None = None) -> None:
        self.log_path = log_path
        self.stream = stream if stream is not None else sys.stdout
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, context: LogContext, stage: str, message: str) -> None:
        line = (
            "[HT-LAB "
            f"attempt={context.attempt_id} "
            f"branch={context.branch_id} "
            f"test={context.test_id} "
            f"stage={stage}] "
            f"{message}"
        )
        print(line, file=self.stream, flush=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
