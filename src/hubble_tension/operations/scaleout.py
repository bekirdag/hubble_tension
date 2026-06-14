from __future__ import annotations

from hubble_tension.schemas.operations import ScaleOutProfile


def default_scale_out_profile(*, enabled: bool = False, worker_count: int = 0) -> ScaleOutProfile:
    return ScaleOutProfile(
        profile_id="default-scale-out",
        enabled=enabled,
        worker_count=worker_count,
        allowed_job_types=("sweep", "posterior", "replication", "adversarial"),
        preserves_sandbox=True,
        preserves_provenance=True,
        preserves_metric_gates=True,
        preserves_replication_gates=True,
        preserves_adversarial_gates=True,
    )
