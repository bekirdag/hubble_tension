from __future__ import annotations

from importlib import import_module

PHASE0_NAMESPACES = (
    "runtime",
    "state",
    "corpus",
    "concept_forge",
    "equations",
    "validation",
    "runners",
    "solvers",
    "reporting",
    "generated_models",
    "compressed_obs",
    "replication",
    "adversarial",
    "operations",
    "readiness",
)


def test_package_imports_cleanly() -> None:
    import_module("hubble_tension")


def test_phase0_namespace_packages_import_cleanly() -> None:
    for namespace in PHASE0_NAMESPACES:
        import_module(f"hubble_tension.{namespace}")
