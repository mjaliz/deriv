from __future__ import annotations

import json
import re
from pathlib import Path

from constants import LLMStage, REQUIRED_BRIEFING_SECTIONS
from models import (
    AuditLogArtifact,
    ChangeVelocityReport,
    ChunkingLogArtifact,
    ContradictionsOutput,
    CorpusArtifact,
    HallucinationValidationOutput,
    JurisdictionTagsOutput,
    LLMCallRecord,
    RiskBriefingOutput,
    SemanticDiffOutput,
    SourcesConfig,
    StakeholderRoutingOutput,
)


class ArtifactValidationError(RuntimeError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("\n".join(errors))
        self.errors = errors


def validate_artifacts(
    output_dir: Path,
    source_file: Path = Path("sources.json"),
    previous_snapshot_file: Path = Path("previous_snapshot_document_a.txt"),
) -> None:
    errors: list[str] = []
    output_dir = output_dir.resolve()

    for required_input in [source_file, previous_snapshot_file]:
        if not required_input.exists():
            errors.append(f"missing input artifact: {required_input}")

    generated_files = [
        "corpus.json",
        "chunking_log.json",
        "semantic_diff.json",
        "contradictions.json",
        "risk_briefing_draft.md",
        "risk_briefing.md",
        "stakeholder_routing.json",
        "audit_log.json",
        "hallucination_validation.json",
        "jurisdiction_tags.json",
        "change_velocity_report.json",
        "llm_calls.jsonl",
    ]
    for filename in generated_files:
        if not (output_dir / filename).exists():
            errors.append(f"missing generated artifact: {filename}")

    if errors:
        raise ArtifactValidationError(errors)

    sources = _load_model(source_file, SourcesConfig, errors)
    corpus = _load_model(output_dir / "corpus.json", CorpusArtifact, errors)
    chunks = _load_model(output_dir / "chunking_log.json", ChunkingLogArtifact, errors)
    semantic = _load_model(output_dir / "semantic_diff.json", SemanticDiffOutput, errors)
    contradictions = _load_model(output_dir / "contradictions.json", ContradictionsOutput, errors)
    routing = _load_model(output_dir / "stakeholder_routing.json", StakeholderRoutingOutput, errors)
    audit = _load_model(output_dir / "audit_log.json", AuditLogArtifact, errors)
    hallucination = _load_model(output_dir / "hallucination_validation.json", HallucinationValidationOutput, errors)
    _load_model(output_dir / "jurisdiction_tags.json", JurisdictionTagsOutput, errors)
    _load_model(output_dir / "change_velocity_report.json", ChangeVelocityReport, errors)

    llm_calls = _load_jsonl(output_dir / "llm_calls.jsonl", errors)
    if errors:
        raise ArtifactValidationError(errors)

    assert sources is not None
    assert corpus is not None
    assert chunks is not None
    assert semantic is not None
    assert contradictions is not None
    assert routing is not None
    assert audit is not None
    assert hallucination is not None

    _validate_corpus(sources, corpus, errors)
    _validate_chunking(chunks, errors)
    _validate_llm_calls(llm_calls, errors)
    _validate_finding_section_refs(corpus, semantic, contradictions, hallucination, errors)
    briefing = _validate_briefing_files(output_dir, errors)
    if briefing is not None:
        _validate_stage_dependencies(semantic, contradictions, briefing, routing, errors)
    _validate_routing(routing, errors)
    _validate_audit(audit, errors)
    _validate_hallucination_application(output_dir, hallucination, errors)

    if errors:
        raise ArtifactValidationError(errors)


def _load_model(path: Path, model_class, errors: list[str]):
    try:
        return model_class.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"{path.name} failed validation: {exc}")
        return None


def _load_jsonl(path: Path, errors: list[str]) -> list[LLMCallRecord]:
    calls: list[LLMCallRecord] = []
    try:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            calls.append(LLMCallRecord.model_validate(json.loads(line)))
    except Exception as exc:
        errors.append(f"{path.name} failed JSONL validation: {exc}")
    return calls


def _validate_corpus(sources: SourcesConfig, corpus: CorpusArtifact, errors: list[str]) -> None:
    section_doc_ids = {section.document_id for section in corpus.sections}
    failure_doc_ids = {failure.document_id for failure in corpus.failures}
    for document in sources.documents:
        if document.document_id not in section_doc_ids and document.document_id not in failure_doc_ids:
            errors.append(f"document {document.document_id} has neither sections nor a logged failure")
    for section in corpus.sections:
        expected_prefix = f"{section.document_id}-"
        if not section.section_id.startswith(expected_prefix):
            errors.append(f"section {section.section_id} does not start with {expected_prefix}")
        if section.character_count != len(section.text):
            errors.append(f"section {section.section_id} has incorrect character_count")
        if not section.content_hash:
            errors.append(f"section {section.section_id} is missing content_hash")
    if not corpus.sections:
        errors.append("corpus.json contains no section-level metadata")


def _validate_chunking(chunks: ChunkingLogArtifact, errors: list[str]) -> None:
    stages = {record.stage for record in chunks.records}
    required_stages = {
        LLMStage.SEMANTIC_DIFF.value,
        LLMStage.CONTRADICTIONS.value,
        LLMStage.RISK_BRIEFING.value,
        LLMStage.HALLUCINATION_VALIDATION.value,
        LLMStage.STAKEHOLDER_ROUTING.value,
        LLMStage.JURISDICTION_TAGGING.value,
        LLMStage.CHANGE_VELOCITY_ANALYSIS.value,
    }
    missing = sorted(required_stages - stages)
    if missing:
        errors.append(f"chunking metadata missing stages: {', '.join(missing)}")


def _validate_llm_calls(calls: list[LLMCallRecord], errors: list[str]) -> None:
    stages = {call.stage for call in calls}
    required_stages = {
        LLMStage.SEMANTIC_DIFF.value,
        LLMStage.CONTRADICTIONS.value,
        LLMStage.RISK_BRIEFING.value,
        LLMStage.HALLUCINATION_VALIDATION.value,
        LLMStage.STAKEHOLDER_ROUTING.value,
        LLMStage.JURISDICTION_TAGGING.value,
        LLMStage.CHANGE_VELOCITY_ANALYSIS.value,
    }
    missing = sorted(required_stages - stages)
    if missing:
        errors.append(f"llm_calls.jsonl missing stages: {', '.join(missing)}")


def _validate_finding_section_refs(
    corpus: CorpusArtifact,
    semantic: SemanticDiffOutput,
    contradictions: ContradictionsOutput,
    hallucination: HallucinationValidationOutput,
    errors: list[str],
) -> None:
    section_ids = {section.section_id for section in corpus.sections}
    for change in semantic.changes:
        unknown = set(change.affected_section_ids) - section_ids
        if unknown:
            errors.append(f"semantic change {change.change_id} references unknown sections: {sorted(unknown)}")
    for contradiction in contradictions.contradictions:
        unknown = set(contradiction.source_section_ids) - section_ids
        if unknown:
            errors.append(f"contradiction {contradiction.contradiction_id} references unknown sections: {sorted(unknown)}")
    for claim in hallucination.claims:
        unknown = set(claim.source_section_ids) - section_ids
        if unknown:
            errors.append(f"hallucination validation claim references unknown sections: {sorted(unknown)}")


def _validate_briefing_files(output_dir: Path, errors: list[str]) -> RiskBriefingOutput | None:
    final_text = (output_dir / "risk_briefing.md").read_text(encoding="utf-8")
    draft_text = (output_dir / "risk_briefing_draft.md").read_text(encoding="utf-8")
    for section in REQUIRED_BRIEFING_SECTIONS:
        pattern = rf"^##\s+{re.escape(section)}\s*$"
        if not re.search(pattern, final_text, flags=re.MULTILINE):
            errors.append(f"risk_briefing.md missing section: {section}")
        if not re.search(pattern, draft_text, flags=re.MULTILINE):
            errors.append(f"risk_briefing_draft.md missing section: {section}")
    try:
        actions_match = re.search(r"##\s+Recommended Actions\s*```json\s*(.*?)\s*```", final_text, flags=re.DOTALL)
        if not actions_match:
            actions_match = re.search(r"```json\s*(.*?)\s*```", final_text, flags=re.DOTALL)
        actions = json.loads(actions_match.group(1)) if actions_match else []
        return RiskBriefingOutput(
            executive_summary="validated from markdown",
            material_changes=[],
            cross_document_contradictions=[],
            compliance_risk_level=_extract_risk_level(final_text),
            recommended_actions=actions,
        )
    except Exception as exc:
        errors.append(f"risk_briefing.md recommended actions are not valid JSON actions: {exc}")
        return None


def _extract_risk_level(text: str) -> str:
    match = re.search(r"##\s+Compliance Risk Level\s*(.*?)\n##", text + "\n##", flags=re.DOTALL)
    value = (match.group(1).strip() if match else "Low").splitlines()[0].strip()
    return value if value in {"Low", "Medium", "High"} else "Low"


def _validate_stage_dependencies(
    semantic: SemanticDiffOutput,
    contradictions: ContradictionsOutput,
    briefing: RiskBriefingOutput,
    routing: StakeholderRoutingOutput,
    errors: list[str],
) -> None:
    finding_ids = {change.change_id for change in semantic.changes}
    finding_ids.update(contradiction.contradiction_id for contradiction in contradictions.contradictions)
    for action in briefing.recommended_actions:
        if not action.source_finding_ids:
            errors.append(f"action {action.action_id} does not reference source findings")
        unknown = set(action.source_finding_ids) - finding_ids
        if unknown:
            errors.append(f"action {action.action_id} references unknown findings: {sorted(unknown)}")
    action_ids = {action.action_id for action in briefing.recommended_actions}
    for route in routing.routes:
        unknown_actions = set(route.action_ids) - action_ids
        if unknown_actions:
            errors.append(f"route {route.team} references unknown actions: {sorted(unknown_actions)}")


def _validate_routing(routing: StakeholderRoutingOutput, errors: list[str]) -> None:
    notifications = [route.notification.strip() for route in routing.routes]
    if len(notifications) > 1 and len(set(notifications)) == 1:
        errors.append("stakeholder notifications are identical boilerplate")
    for route in routing.routes:
        if not route.action_ids:
            errors.append(f"route {route.team} has no action_ids")


def _validate_audit(audit: AuditLogArtifact, errors: list[str]) -> None:
    for item in audit.items:
        if not item.artifact_refs:
            errors.append(f"audit item {item.item_id} has no artifact_refs")
        if item.item_type != "hallucination_validation_correction" and not item.source_section_ids:
            errors.append(f"audit item {item.item_id} has no source_section_ids")


def _validate_hallucination_application(
    output_dir: Path,
    hallucination: HallucinationValidationOutput,
    errors: list[str],
) -> None:
    final_text = (output_dir / "risk_briefing.md").read_text(encoding="utf-8")
    for claim in hallucination.claims:
        if claim.grounded:
            continue
        if claim.recommended_correction and claim.recommended_correction not in final_text:
            errors.append(f"ungrounded claim correction was not applied: {claim.claim}")
        if not claim.recommended_correction and claim.claim in final_text:
            errors.append(f"ungrounded claim was not removed: {claim.claim}")
