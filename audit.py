from __future__ import annotations

from models import (
    AuditItem,
    AuditLogArtifact,
    ContradictionsOutput,
    HallucinationValidationOutput,
    RiskBriefingOutput,
    SemanticDiffOutput,
    StakeholderRoutingOutput,
)
from utils import utc_now


def build_audit_log(
    semantic_diff: SemanticDiffOutput,
    contradictions: ContradictionsOutput,
    briefing: RiskBriefingOutput,
    routing: StakeholderRoutingOutput,
    validation: HallucinationValidationOutput,
) -> AuditLogArtifact:
    items: list[AuditItem] = []

    for change in semantic_diff.changes:
        items.append(
            AuditItem(
                item_type="semantic_change",
                item_id=change.change_id,
                summary=change.risk_summary,
                source_section_ids=change.affected_section_ids,
                artifact_refs=["semantic_diff.json"],
            )
        )

    for contradiction in contradictions.contradictions:
        items.append(
            AuditItem(
                item_type="contradiction",
                item_id=contradiction.contradiction_id,
                summary=contradiction.why_it_may_conflict,
                source_section_ids=contradiction.source_section_ids,
                artifact_refs=["contradictions.json"],
            )
        )

    finding_source_sections = _finding_source_sections(semantic_diff, contradictions)
    for action in briefing.recommended_actions:
        source_sections = sorted(
            {
                section_id
                for finding_id in action.source_finding_ids
                for section_id in finding_source_sections.get(finding_id, [])
            }
        )
        items.append(
            AuditItem(
                item_type="recommended_action",
                item_id=action.action_id,
                summary=action.action,
                source_section_ids=source_sections,
                artifact_refs=["risk_briefing_draft.md", "risk_briefing.md"],
            )
        )

    action_source_sections = {
        action.action_id: sorted(
            {
                section_id
                for finding_id in action.source_finding_ids
                for section_id in finding_source_sections.get(finding_id, [])
            }
        )
        for action in briefing.recommended_actions
    }
    for route in routing.routes:
        source_sections = sorted(
            {
                section_id
                for action_id in route.action_ids
                for section_id in action_source_sections.get(action_id, [])
            }
        )
        items.append(
            AuditItem(
                item_type="routing_decision",
                item_id=f"route-{route.team}",
                summary=route.notification,
                source_section_ids=source_sections,
                artifact_refs=["stakeholder_routing.json"],
            )
        )

    for index, claim in enumerate(validation.claims, start=1):
        if claim.grounded:
            continue
        items.append(
            AuditItem(
                item_type="hallucination_validation_correction",
                item_id=f"claim-{index:03d}",
                summary=claim.recommended_correction or claim.issue or claim.claim,
                source_section_ids=claim.source_section_ids,
                artifact_refs=["hallucination_validation.json", "risk_briefing.md"],
            )
        )

    return AuditLogArtifact(generated_at=utc_now(), items=items)


def _finding_source_sections(
    semantic_diff: SemanticDiffOutput,
    contradictions: ContradictionsOutput,
) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for change in semantic_diff.changes:
        mapping[change.change_id] = change.affected_section_ids
    for contradiction in contradictions.contradictions:
        mapping[contradiction.contradiction_id] = contradiction.source_section_ids
    return mapping
