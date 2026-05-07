from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from constants import (
    ALLOWED_CHANGE_TYPES,
    ALLOWED_CONFIDENCE,
    ALLOWED_CONTRADICTION_SEVERITIES,
    ALLOWED_JURISDICTIONS,
    ALLOWED_PRIORITIES,
    ALLOWED_RISK_LEVELS,
    ALLOWED_SEVERITIES,
    ALLOWED_TEAMS,
)


ChangeType = Literal["addition", "removal", "modification", "clarification", "no_material_change"]
Severity = Literal["critical", "major", "minor", "none"]
ContradictionSeverity = Literal["critical", "major", "minor"]
RiskLevel = Literal["Low", "Medium", "High"]
Team = Literal["Legal", "Risk", "Product", "Marketing", "Engineering", "Customer Support"]
Priority = Literal["P0", "P1", "P2", "P3"]
Confidence = Literal["low", "medium", "high"]
Jurisdiction = Literal["EU", "BVI", "Malta", "global", "unknown"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DocumentSource(StrictModel):
    document_id: str
    name: str
    url: str


class SourcesConfig(StrictModel):
    documents: list[DocumentSource]

    @field_validator("documents")
    @classmethod
    def validate_unique_document_ids(cls, documents: list[DocumentSource]) -> list[DocumentSource]:
        ids = [document.document_id for document in documents]
        if len(ids) != len(set(ids)):
            raise ValueError("document_id values must be unique")
        return documents


class FetchFailure(StrictModel):
    document_id: str
    document_name: str
    source_url: str
    stage: str
    error: str


class CorpusDocumentStatus(StrictModel):
    document_id: str
    document_name: str
    source_url: str
    fetched: bool
    section_count: int
    failure: str | None = None


class CorpusSection(StrictModel):
    document_id: str
    document_name: str
    source_url: str
    section_id: str
    section_title: str
    text: str
    character_count: int
    content_hash: str


class CorpusArtifact(StrictModel):
    generated_at: str
    documents: list[CorpusDocumentStatus]
    sections: list[CorpusSection]
    failures: list[FetchFailure] = Field(default_factory=list)


class ChunkingRecord(StrictModel):
    stage: str
    batch_number: int
    input_artifacts: list[str]
    included_section_ids: list[str]
    omitted_section_ids: list[str]
    selection_reason: str
    included_character_count: int
    max_character_budget: int


class ChunkingLogArtifact(StrictModel):
    generated_at: str
    records: list[ChunkingRecord]


class LLMCallRecord(StrictModel):
    stage: str
    timestamp: str
    provider: str
    model: str
    prompt_hash: str
    input_artifacts: list[str]
    output_artifact: str
    section_ids_included: list[str]


class SemanticChange(StrictModel):
    change_id: str
    type: ChangeType
    severity: Severity
    before: str
    after: str
    affected_section_ids: list[str]
    jurisdiction: str | None = None
    risk_summary: str

    @field_validator("type")
    @classmethod
    def validate_change_type(cls, value: str) -> str:
        if value not in ALLOWED_CHANGE_TYPES:
            raise ValueError(f"invalid change type: {value}")
        return value

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, value: str) -> str:
        if value not in ALLOWED_SEVERITIES:
            raise ValueError(f"invalid severity: {value}")
        return value


class SemanticDiffOutput(StrictModel):
    changes: list[SemanticChange]


class ContradictionFinding(StrictModel):
    contradiction_id: str
    documents_involved: list[str]
    source_section_ids: list[str]
    statement_a: str
    statement_b: str
    why_it_may_conflict: str
    severity: ContradictionSeverity
    confidence: Confidence

    @field_validator("severity")
    @classmethod
    def validate_contradiction_severity(cls, value: str) -> str:
        if value not in ALLOWED_CONTRADICTION_SEVERITIES:
            raise ValueError(f"invalid contradiction severity: {value}")
        return value

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: str) -> str:
        if value not in ALLOWED_CONFIDENCE:
            raise ValueError(f"invalid confidence: {value}")
        return value


class ContradictionsOutput(StrictModel):
    contradictions: list[ContradictionFinding]
    explanation_if_fewer_than_two: str | None = None


class RecommendedAction(StrictModel):
    action_id: str
    action: str
    owner_type: Team
    priority: Priority
    source_finding_ids: list[str]

    @field_validator("owner_type")
    @classmethod
    def validate_owner_type(cls, value: str) -> str:
        if value not in ALLOWED_TEAMS:
            raise ValueError(f"invalid owner_type: {value}")
        return value

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, value: str) -> str:
        if value not in ALLOWED_PRIORITIES:
            raise ValueError(f"invalid priority: {value}")
        return value


class RiskBriefingOutput(StrictModel):
    executive_summary: str
    material_changes: list[str]
    cross_document_contradictions: list[str]
    compliance_risk_level: RiskLevel
    recommended_actions: list[RecommendedAction]

    @field_validator("compliance_risk_level")
    @classmethod
    def validate_risk_level(cls, value: str) -> str:
        if value not in ALLOWED_RISK_LEVELS:
            raise ValueError(f"invalid compliance risk level: {value}")
        return value


class StakeholderRoute(StrictModel):
    team: Team
    action_ids: list[str]
    notification: str

    @field_validator("team")
    @classmethod
    def validate_team(cls, value: str) -> str:
        if value not in ALLOWED_TEAMS:
            raise ValueError(f"invalid team: {value}")
        return value


class StakeholderRoutingOutput(StrictModel):
    routes: list[StakeholderRoute]


class ClaimValidation(StrictModel):
    claim: str
    grounded: bool
    source_section_ids: list[str]
    issue: str | None = None
    recommended_correction: str | None = None


class HallucinationValidationOutput(StrictModel):
    claims: list[ClaimValidation]


class JurisdictionTag(StrictModel):
    section_id: str
    jurisdiction: Jurisdiction
    rationale: str

    @field_validator("jurisdiction")
    @classmethod
    def validate_jurisdiction(cls, value: str) -> str:
        if value not in ALLOWED_JURISDICTIONS:
            raise ValueError(f"invalid jurisdiction: {value}")
        return value


class JurisdictionTagsOutput(StrictModel):
    tags: list[JurisdictionTag]


class ChangeVelocityReport(StrictModel):
    current_run_timestamp: str
    previous_run_timestamp: str
    material_changes_detected: int
    days_between_runs: int
    extrapolated_material_changes_per_30_days: float


class AuditItem(StrictModel):
    item_type: str
    item_id: str
    summary: str
    source_section_ids: list[str]
    artifact_refs: list[str]


class AuditLogArtifact(StrictModel):
    generated_at: str
    items: list[AuditItem]


def validate_controlled_vocabularies() -> None:
    missing = [
        ("change types", ALLOWED_CHANGE_TYPES),
        ("severities", ALLOWED_SEVERITIES),
        ("contradiction severities", ALLOWED_CONTRADICTION_SEVERITIES),
        ("risk levels", ALLOWED_RISK_LEVELS),
        ("teams", ALLOWED_TEAMS),
        ("priorities", ALLOWED_PRIORITIES),
        ("confidence values", ALLOWED_CONFIDENCE),
        ("jurisdictions", ALLOWED_JURISDICTIONS),
    ]
    for label, values in missing:
        if not values:
            raise ValueError(f"controlled vocabulary is empty: {label}")
