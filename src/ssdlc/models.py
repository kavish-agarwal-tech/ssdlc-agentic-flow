"""JSON domain contracts. Providers cannot set approval or execution state."""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def uid() -> str:
    return uuid4().hex


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Validity(StrEnum):
    VALID = "VALID"
    REVALIDATE = "REVALIDATE"
    INVALIDATED = "INVALIDATED"
    SUPERSEDED = "SUPERSEDED"


class Question(Model):
    id: str
    classification: Literal[
        "BLOCKING_AMBIGUITY",
        "NON_BLOCKING_AMBIGUITY",
        "PROPOSED_DEFAULT",
        "ASSUMPTION_REQUIRING_APPROVAL",
    ]
    unclear: str
    why_it_matters: str
    options: list[str] = Field(min_length=2)
    recommendation: str
    reasoning: str
    recommendation_is_binding: Literal[False] = False
    human_confirmation_required: bool = True


class Criterion(Model):
    id: str
    requirement_ref: str
    description: str


class Requirement(Model):
    original_text: str
    normalized_requirement: str
    functional_requirements: dict[str, str]
    non_functional_requirements: dict[str, str]
    invariants: list[str]
    assumptions: list[str]
    open_questions: list[Question]
    acceptance_criteria: list[Criterion] = Field(min_length=1)
    changes_from_previous_version: list[str] = Field(default_factory=list)
    reason_for_change: str = "Initial analysis"
    initiating_actor: str = "requirement_agent"
    human_input: dict[str, str] = Field(default_factory=dict)
    decisions: dict[str, str] = Field(default_factory=dict)


class Alternative(Model):
    description: str
    advantages: list[str]
    disadvantages: list[str]
    complexity: str
    operational_impact: str
    security_impact: str
    reliability_impact: str
    scalability_impact: str
    cost_implication: str


class ADR(Model):
    adr_id: str
    decision: str
    context: str
    alternatives: list[Alternative] = Field(min_length=2)
    recommendation: str
    tradeoffs: list[str]
    rationale: str
    requirement_refs: list[str]
    review_refs: list[str] = Field(default_factory=list)
    decision_owner: str = "human"
    affected_artifacts: list[str]


class Architecture(Model):
    sections: dict[str, str]
    requirement_mapping: dict[str, str]
    technology_stack: dict[str, str]
    adrs: list[ADR] = Field(min_length=1)


ARCHITECTURE_SECTIONS = {
    "context",
    "scope",
    "goals",
    "constraints",
    "assumptions",
    "target_state",
    "components",
    "responsibilities",
    "data_ownership",
    "system_of_record",
    "interfaces",
    "data_model",
    "consistency",
    "scalability",
    "performance",
    "reliability",
    "availability",
    "observability",
    "security",
    "failure_behavior",
    "resiliency",
    "deployment",
    "operations",
    "risks",
    "alternatives",
    "tradeoffs",
    "open_decisions",
}


class WorkItem(Model):
    id: str
    title: str
    depends_on: list[str]
    requirement_refs: list[str]
    acceptance_criteria: list[str] = Field(min_length=1)
    design: dict[str, str]
    risks: list[str]


class Plan(Model):
    slices: list[WorkItem] = Field(min_length=1)
    rationale: str
    proposed_scope_changes: list[str] = Field(default_factory=list)


DESIGN_SECTIONS = {
    "layout",
    "components",
    "interfaces",
    "contracts",
    "data_structures",
    "persistence",
    "validation",
    "errors",
    "concurrency",
    "sequence",
    "logging",
    "metrics",
    "test_seams",
    "implementation_notes",
}


class FileBundle(Model):
    files: dict[str, str] = Field(min_length=1)
    change_summary: str
    criterion_tests: dict[str, list[str]] = Field(default_factory=dict)
    deviations: list[str] = Field(default_factory=list)


class FindingProposal(Model):
    id: str
    category: str
    severity: Literal["BLOCKER", "HIGH", "MEDIUM", "LOW"]
    description: str
    rationale: str
    affected_component: str
    suggested_resolution: str


class Resolution(Model):
    finding_id: str
    author_response: str
    actual_change: str
    resolution_reason: str
    reviewer_verification: str


class Review(Model):
    complete: bool
    findings: list[FindingProposal]
    resolutions: list[Resolution] = Field(default_factory=list)


class Finding(FindingProposal):
    artifact_id: str
    artifact_version: int
    status: Literal[
        "OPEN", "IN_DISCUSSION", "RESOLVED", "DEFERRED", "ACCEPTED_RISK", "REJECTED_WITH_RATIONALE"
    ] = "OPEN"
    author_response: str = ""
    actual_change: str = ""
    before_version: int | None = None
    after_version: int | None = None
    resolution_reason: str = ""
    reviewer_verification: str = ""
    created_at: str = Field(default_factory=now)
    updated_at: str = Field(default_factory=now)


class FailureAnalysis(Model):
    category: Literal[
        "IMPLEMENTATION_DEFECT",
        "TEST_DEFECT",
        "DESIGN_DEFECT",
        "ARCHITECTURE_DEFECT",
        "REQUIREMENT_DEFECT",
        "ENVIRONMENT_OR_TOOLING",
    ]
    evidence: list[str] = Field(min_length=1)
    reasoning: str


class Impact(Model):
    affected_modules: list[str]
    services: list[str]
    apis: list[str]
    data_flows: list[str]
    persistence_impact: str
    test_impact: str
    configuration_impact: str
    backward_compatibility: str
    migration_requirements: str
    regression_risk: str


class Document(Model):
    sections: dict[str, str]


class Artifact(Model):
    id: str
    version: int
    kind: str
    content: dict[str, Any]
    dependencies: list[str] = Field(default_factory=list)
    validity: Validity = Validity.VALID
    approval_status: Literal[
        "DRAFT", "READY_FOR_APPROVAL", "APPROVED", "REJECTED", "SUPERSEDED"
    ] = "DRAFT"
    approver: str | None = None
    approval_timestamp: str | None = None
    created_at: str = Field(default_factory=now)
    digest: str

    @property
    def ref(self) -> str:
        return f"{self.id}@{self.version}"


class HumanDecision(Model):
    actor: str = Field(min_length=1)
    action: Literal[
        "approve", "reject", "clarify", "revise", "retry", "rollback", "abort", "accept_risk"
    ]
    rationale: str = Field(min_length=1)
    artifact_ref: str | None = None
    answers: dict[str, str] = Field(default_factory=dict)
    finding_ids: list[str] = Field(default_factory=list)
    target_ref: str | None = None
    revision_target: Literal["requirement", "planning_design"] | None = None


class Approval(Model):
    id: str = Field(default_factory=uid)
    artifact_ref: str
    actor: str
    decision: str
    rationale: str
    timestamp: str = Field(default_factory=now)


class ToolResult(Model):
    id: str = Field(default_factory=uid)
    tool: str
    command: list[str]
    cwd: str
    exit_status: int
    duration: float
    output_summary: str
    artifact_refs: list[str]
    environment: dict[str, str]
    workspace_digest: str
    created_at: str = Field(default_factory=now)


class AuditEvent(Model):
    event_id: str = Field(default_factory=uid)
    workflow_id: str
    timestamp: str = Field(default_factory=now)
    actor_type: str = "orchestrator"
    actor_id: str = "ssdlc"
    action: str
    stage: str
    artifact_refs: list[str] = Field(default_factory=list)
    before_version: int | None = None
    after_version: int | None = None
    rationale: str = ""
    related_review_ids: list[str] = Field(default_factory=list)
    related_adr_ids: list[str] = Field(default_factory=list)
    related_approval_ids: list[str] = Field(default_factory=list)
    correlation_id: str = ""
