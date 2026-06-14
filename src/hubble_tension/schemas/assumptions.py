from __future__ import annotations

from pydantic import Field, model_validator

from hubble_tension.schemas.base import StrictBaseModel


class AssumptionDiff(StrictBaseModel):
    kept: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    added: list[str] = Field(default_factory=list)
    modified: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_visible_assumptions(self) -> AssumptionDiff:
        if not any((self.kept, self.removed, self.added, self.modified)):
            msg = "assumption diff must record at least one kept, removed, added, or modified item"
            raise ValueError(msg)
        return self
