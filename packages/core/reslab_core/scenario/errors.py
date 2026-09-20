from __future__ import annotations

from pydantic import BaseModel, Field


class ValidationIssue(BaseModel):
    path: str = Field(description="Location in the scenario document, e.g. 'events[2].inject'")
    message: str
    severity: str = Field(default="error", pattern="^(error|warning)$")
    code: str = Field(default="invalid")


class ScenarioValidationError(ValueError):
    """Raised when a scenario document cannot be accepted for execution."""

    def __init__(self, issues: list[ValidationIssue]) -> None:
        self.issues = issues
        summary = "; ".join(f"{i.path}: {i.message}" for i in issues[:5])
        more = f" (+{len(issues) - 5} more)" if len(issues) > 5 else ""
        super().__init__(f"scenario validation failed: {summary}{more}")

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]
