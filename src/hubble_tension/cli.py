from __future__ import annotations

import sys
from collections.abc import Sequence

from hubble_tension.runtime import RuntimeSupervisor


def main(argv: Sequence[str] | None = None) -> int:
    """No-prompt launcher entry point."""

    _ = list(sys.argv[1:] if argv is None else argv)
    result = RuntimeSupervisor().run()
    return result.exit_code
