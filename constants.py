from __future__ import annotations

from enum import StrEnum


ALLOWED_CHANGE_TYPES = {
    "addition",
    "removal",
    "modification",
    "clarification",
    "no_material_change",
}

ALLOWED_SEVERITIES = {"critical", "major", "minor", "none"}
ALLOWED_CONTRADICTION_SEVERITIES = {"critical", "major", "minor"}
ALLOWED_RISK_LEVELS = {"Low", "Medium", "High"}
ALLOWED_TEAMS = {
    "Legal",
    "Risk",
    "Product",
    "Marketing",
    "Engineering",
    "Customer Support",
}
ALLOWED_PRIORITIES = {"P0", "P1", "P2", "P3"}
ALLOWED_CONFIDENCE = {"low", "medium", "high"}
ALLOWED_JURISDICTIONS = {"EU", "BVI", "Malta", "global", "unknown"}


class Stage(StrEnum):
    INIT = "INIT"
    SOURCES_LOADED = "SOURCES_LOADED"
    LIVE_DOCUMENTS_FETCHED = "LIVE_DOCUMENTS_FETCHED"
    DOCUMENTS_CLEANED = "DOCUMENTS_CLEANED"
    DOCUMENTS_SEGMENTED = "DOCUMENTS_SEGMENTED"
    SNAPSHOT_DIFF_COMPLETE = "SNAPSHOT_DIFF_COMPLETE"
    CROSS_DOCUMENT_CHECK_COMPLETE = "CROSS_DOCUMENT_CHECK_COMPLETE"
    RISK_BRIEFING_DRAFTED = "RISK_BRIEFING_DRAFTED"
    HALLUCINATION_VALIDATED = "HALLUCINATION_VALIDATED"
    FINAL_BRIEFING_WRITTEN = "FINAL_BRIEFING_WRITTEN"
    STAKEHOLDER_ROUTING_COMPLETE = "STAKEHOLDER_ROUTING_COMPLETE"
    AUDIT_LOG_EXPORTED = "AUDIT_LOG_EXPORTED"
    VALIDATION_COMPLETE = "VALIDATION_COMPLETE"
    RESULTS_FINALISED = "RESULTS_FINALISED"


STAGE_ORDER = [
    Stage.INIT,
    Stage.SOURCES_LOADED,
    Stage.LIVE_DOCUMENTS_FETCHED,
    Stage.DOCUMENTS_CLEANED,
    Stage.DOCUMENTS_SEGMENTED,
    Stage.SNAPSHOT_DIFF_COMPLETE,
    Stage.CROSS_DOCUMENT_CHECK_COMPLETE,
    Stage.RISK_BRIEFING_DRAFTED,
    Stage.HALLUCINATION_VALIDATED,
    Stage.FINAL_BRIEFING_WRITTEN,
    Stage.STAKEHOLDER_ROUTING_COMPLETE,
    Stage.AUDIT_LOG_EXPORTED,
    Stage.VALIDATION_COMPLETE,
    Stage.RESULTS_FINALISED,
]


class LLMStage(StrEnum):
    SEMANTIC_DIFF = Stage.SNAPSHOT_DIFF_COMPLETE.value
    CONTRADICTIONS = Stage.CROSS_DOCUMENT_CHECK_COMPLETE.value
    RISK_BRIEFING = Stage.RISK_BRIEFING_DRAFTED.value
    HALLUCINATION_VALIDATION = Stage.HALLUCINATION_VALIDATED.value
    STAKEHOLDER_ROUTING = Stage.STAKEHOLDER_ROUTING_COMPLETE.value
    JURISDICTION_TAGGING = "JURISDICTION_TAGGING"
    CHANGE_VELOCITY_ANALYSIS = "CHANGE_VELOCITY_ANALYSIS"


TEAM_RESPONSIBILITIES = {
    "Legal": "Owns regulatory interpretation, terms updates, and approvals for externally visible compliance language.",
    "Risk": "Assesses customer, market, operational, and regulatory exposure from policy changes or inconsistencies.",
    "Product": "Owns product behavior, account workflows, limits, eligibility, and customer-facing feature implications.",
    "Marketing": "Owns public website messaging, campaign copy, claims, disclaimers, and page consistency.",
    "Engineering": "Owns implementation work, data flows, integrations, account controls, and release changes.",
    "Customer Support": "Owns customer-facing explanations, macros, escalation paths, and support readiness.",
}


REQUIRED_BRIEFING_SECTIONS = [
    "Executive Summary",
    "Material Changes",
    "Cross-Document Contradictions",
    "Compliance Risk Level",
    "Recommended Actions",
]
