from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from audit import build_audit_log
from briefing import apply_validation_corrections, render_risk_briefing
from chunking import ChunkPlanner
from constants import (
    ALLOWED_CHANGE_TYPES,
    ALLOWED_PRIORITIES,
    ALLOWED_RISK_LEVELS,
    ALLOWED_SEVERITIES,
    ALLOWED_TEAMS,
    LLMStage,
    Stage,
    TEAM_RESPONSIBILITIES,
)
from ingestion import build_corpus, fetch_live_documents
from llm import PROMPTS_BY_STAGE, StructuredLLM
from models import (
    ChangeVelocityReport,
    ContradictionsOutput,
    CorpusArtifact,
    CorpusSection,
    HallucinationValidationOutput,
    JurisdictionTagsOutput,
    RiskBriefingOutput,
    SemanticChange,
    SemanticDiffOutput,
    SourcesConfig,
    StakeholderRoutingOutput,
    validate_controlled_vocabularies,
)
from settings import Settings
from stage_tracker import StageTracker
from utils import model_to_jsonable, read_json, stable_hash, utc_now, write_json
from validation import validate_artifacts


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the staged compliance diff pipeline.")
    parser.add_argument("--mock-llm", action="store_true", help="Use deterministic local structured responses.")
    parser.add_argument("--output-dir", help="Override OUTPUT_DIR.")
    parser.add_argument("--source-file", help="Override SOURCE_FILE.")
    parser.add_argument("--previous-snapshot-file", help="Override PREVIOUS_SNAPSHOT_FILE.")
    args = parser.parse_args()

    settings = Settings()
    overrides: dict[str, Any] = {}
    if args.mock_llm:
        overrides["mock_llm"] = True
    if args.output_dir:
        overrides["output_dir"] = Path(args.output_dir)
    if args.source_file:
        overrides["source_file"] = Path(args.source_file)
    if args.previous_snapshot_file:
        overrides["previous_snapshot_file"] = Path(args.previous_snapshot_file)
    if overrides:
        settings = settings.model_copy(update=overrides)

    configure_logging(settings)
    run_pipeline(settings)


def configure_logging(settings: Settings) -> None:
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(sys.stderr, level=settings.log_level)
    logger.add(settings.output_dir / settings.log_file, level=settings.log_level, rotation="1 MB")


def run_pipeline(settings: Settings) -> None:
    validate_controlled_vocabularies()
    output_dir = settings.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    llm_log_path = output_dir / "llm_calls.jsonl"
    llm_log_path.write_text("", encoding="utf-8")

    tracker = StageTracker()
    logger.info("Starting compliance diff pipeline")

    sources = SourcesConfig.model_validate_json(settings.source_file.read_text(encoding="utf-8"))
    previous_snapshot = settings.previous_snapshot_file.read_text(encoding="utf-8")
    tracker.advance(Stage.SOURCES_LOADED)

    fetched_documents = fetch_live_documents(sources, settings)
    tracker.advance(Stage.LIVE_DOCUMENTS_FETCHED)

    corpus = build_corpus(fetched_documents, settings)
    tracker.advance(Stage.DOCUMENTS_CLEANED)
    tracker.advance(Stage.DOCUMENTS_SEGMENTED)
    write_json(output_dir / "corpus.json", corpus)

    chunker = ChunkPlanner(settings)
    llm = StructuredLLM(settings, llm_log_path)

    jurisdiction_tags = run_jurisdiction_tagging(corpus, chunker, llm, output_dir)
    semantic_diff = run_semantic_diff(
        corpus,
        previous_snapshot,
        jurisdiction_tags,
        chunker,
        llm,
        output_dir,
    )
    tracker.advance(Stage.SNAPSHOT_DIFF_COMPLETE)

    contradictions = run_contradiction_detection(corpus, chunker, llm, output_dir)
    tracker.advance(Stage.CROSS_DOCUMENT_CHECK_COMPLETE)

    briefing = run_risk_briefing(corpus, semantic_diff, contradictions, chunker, llm, output_dir)
    tracker.advance(Stage.RISK_BRIEFING_DRAFTED)

    validation = run_hallucination_validation(
        corpus,
        semantic_diff,
        contradictions,
        briefing,
        chunker,
        llm,
        output_dir,
    )
    tracker.advance(Stage.HALLUCINATION_VALIDATED)

    draft_text = (output_dir / "risk_briefing_draft.md").read_text(encoding="utf-8")
    final_text = apply_validation_corrections(draft_text, validation)
    (output_dir / "risk_briefing.md").write_text(final_text, encoding="utf-8")
    tracker.advance(Stage.FINAL_BRIEFING_WRITTEN)

    routing = run_stakeholder_routing(briefing, chunker, llm, output_dir)
    tracker.advance(Stage.STAKEHOLDER_ROUTING_COMPLETE)

    run_change_velocity_analysis(corpus, semantic_diff, chunker, llm, settings, output_dir)

    audit_log = build_audit_log(semantic_diff, contradictions, briefing, routing, validation)
    write_json(output_dir / "audit_log.json", audit_log)
    tracker.advance(Stage.AUDIT_LOG_EXPORTED)

    write_json(output_dir / "chunking_log.json", chunker.artifact())
    validate_artifacts(output_dir, settings.source_file, settings.previous_snapshot_file)
    tracker.advance(Stage.VALIDATION_COMPLETE)
    tracker.advance(Stage.RESULTS_FINALISED)
    logger.info("Pipeline complete: {}", ", ".join(tracker.completed))


def run_jurisdiction_tagging(
    corpus: CorpusArtifact,
    chunker: ChunkPlanner,
    llm: StructuredLLM,
    output_dir: Path,
) -> JurisdictionTagsOutput:
    stage = LLMStage.JURISDICTION_TAGGING.value
    selected = chunker.select_sections(
        stage=stage,
        sections=corpus.sections,
        input_artifacts=["corpus.json"],
        reason="Selected Document A sections for jurisdiction tagging before semantic diff.",
        document_ids={"A"},
    )
    payload = {
        "allowed_jurisdictions": ["EU", "BVI", "Malta", "global", "unknown"],
        "sections": _sections_payload(selected),
    }
    result = llm.call(
        stage=stage,
        system_prompt=PROMPTS_BY_STAGE[stage],
        payload=payload,
        response_model=JurisdictionTagsOutput,
        input_artifacts=["corpus.json"],
        output_artifact="jurisdiction_tags.json",
        section_ids_included=[section.section_id for section in selected],
    )
    write_json(output_dir / "jurisdiction_tags.json", result)
    return result


def run_semantic_diff(
    corpus: CorpusArtifact,
    previous_snapshot: str,
    jurisdiction_tags: JurisdictionTagsOutput,
    chunker: ChunkPlanner,
    llm: StructuredLLM,
    output_dir: Path,
) -> SemanticDiffOutput:
    stage = LLMStage.SEMANTIC_DIFF.value
    selected = chunker.select_sections(
        stage=stage,
        sections=corpus.sections,
        input_artifacts=["previous_snapshot_document_a.txt", "corpus.json", "jurisdiction_tags.json"],
        reason="Selected current Document A sections and jurisdiction metadata for semantic comparison to the prior snapshot.",
        document_ids={"A"},
    )
    payload = {
        "previous_snapshot": previous_snapshot,
        "current_sections": _sections_payload(selected),
        "jurisdiction_tags": model_to_jsonable(jurisdiction_tags.tags),
        "allowed_change_types": sorted(ALLOWED_CHANGE_TYPES),
        "allowed_severities": sorted(ALLOWED_SEVERITIES),
        "required_behavior": (
            "Compare meaning, obligation, scope, regulatory position, jurisdictional applicability, "
            "and user-facing commitment. Do not perform character-level diffing only."
        ),
    }
    result = llm.call(
        stage=stage,
        system_prompt=PROMPTS_BY_STAGE[stage],
        payload=payload,
        response_model=SemanticDiffOutput,
        input_artifacts=["previous_snapshot_document_a.txt", "corpus.json", "jurisdiction_tags.json"],
        output_artifact="semantic_diff.json",
        section_ids_included=[section.section_id for section in selected],
    )
    result = _ensure_semantic_diff_shape(result, selected, jurisdiction_tags)
    write_json(output_dir / "semantic_diff.json", result)
    return result


def run_contradiction_detection(
    corpus: CorpusArtifact,
    chunker: ChunkPlanner,
    llm: StructuredLLM,
    output_dir: Path,
) -> ContradictionsOutput:
    stage = LLMStage.CONTRADICTIONS.value
    selected = chunker.select_sections(
        stage=stage,
        sections=corpus.sections,
        input_artifacts=["corpus.json"],
        reason="Selected balanced sections from all live documents for simultaneous cross-document consistency review.",
        balanced=True,
    )
    payload = {
        "sections": _sections_payload(selected),
        "allowed_severities": ["critical", "major", "minor"],
        "allowed_confidence_values": ["low", "medium", "high"],
        "required_behavior": (
            "Identify inconsistent, contradictory, or operationally tense statements across documents. "
            "If fewer than two findings are supported, explain why."
        ),
    }
    result = llm.call(
        stage=stage,
        system_prompt=PROMPTS_BY_STAGE[stage],
        payload=payload,
        response_model=ContradictionsOutput,
        input_artifacts=["corpus.json"],
        output_artifact="contradictions.json",
        section_ids_included=[section.section_id for section in selected],
    )
    if len(result.contradictions) < 2 and not result.explanation_if_fewer_than_two:
        result.explanation_if_fewer_than_two = (
            "Fewer than two candidate contradictions were identified by the model from the selected sections."
        )
    write_json(output_dir / "contradictions.json", result)
    return result


def run_risk_briefing(
    corpus: CorpusArtifact,
    semantic_diff: SemanticDiffOutput,
    contradictions: ContradictionsOutput,
    chunker: ChunkPlanner,
    llm: StructuredLLM,
    output_dir: Path,
) -> RiskBriefingOutput:
    stage = LLMStage.RISK_BRIEFING.value
    cited_section_ids = _source_section_ids_for_findings(semantic_diff, contradictions)
    selected = chunker.select_sections(
        stage=stage,
        sections=corpus.sections,
        input_artifacts=["semantic_diff.json", "contradictions.json", "corpus.json"],
        reason="Selected source sections cited by Stage 1 and Stage 2 findings for grounded briefing generation.",
        section_ids=cited_section_ids,
    )
    payload = {
        "semantic_diff": model_to_jsonable(semantic_diff),
        "contradictions": model_to_jsonable(contradictions),
        "source_sections": _sections_payload(selected),
        "allowed_risk_levels": sorted(ALLOWED_RISK_LEVELS),
        "allowed_teams": sorted(ALLOWED_TEAMS),
        "allowed_priorities": sorted(ALLOWED_PRIORITIES),
    }
    result = llm.call(
        stage=stage,
        system_prompt=PROMPTS_BY_STAGE[stage],
        payload=payload,
        response_model=RiskBriefingOutput,
        input_artifacts=["semantic_diff.json", "contradictions.json", "corpus.json"],
        output_artifact="risk_briefing_draft.md",
        section_ids_included=[section.section_id for section in selected],
    )
    draft = render_risk_briefing(result)
    (output_dir / "risk_briefing_draft.md").write_text(draft, encoding="utf-8")
    return result


def run_hallucination_validation(
    corpus: CorpusArtifact,
    semantic_diff: SemanticDiffOutput,
    contradictions: ContradictionsOutput,
    briefing: RiskBriefingOutput,
    chunker: ChunkPlanner,
    llm: StructuredLLM,
    output_dir: Path,
) -> HallucinationValidationOutput:
    stage = LLMStage.HALLUCINATION_VALIDATION.value
    draft = (output_dir / "risk_briefing_draft.md").read_text(encoding="utf-8")
    cited_section_ids = _source_section_ids_for_findings(semantic_diff, contradictions)
    selected = chunker.select_sections(
        stage=stage,
        sections=corpus.sections,
        input_artifacts=["risk_briefing_draft.md", "semantic_diff.json", "contradictions.json", "corpus.json"],
        reason="Selected source sections cited by findings and actions for claim-level grounding validation.",
        section_ids=cited_section_ids,
    )
    payload = {
        "risk_briefing_draft": draft,
        "semantic_diff": model_to_jsonable(semantic_diff),
        "contradictions": model_to_jsonable(contradictions),
        "recommended_actions": model_to_jsonable(briefing.recommended_actions),
        "source_section_ids": [section.section_id for section in selected],
        "source_sections": _sections_payload(selected),
    }
    result = llm.call(
        stage=stage,
        system_prompt=PROMPTS_BY_STAGE[stage],
        payload=payload,
        response_model=HallucinationValidationOutput,
        input_artifacts=["risk_briefing_draft.md", "semantic_diff.json", "contradictions.json", "corpus.json"],
        output_artifact="hallucination_validation.json",
        section_ids_included=[section.section_id for section in selected],
    )
    write_json(output_dir / "hallucination_validation.json", result)
    return result


def run_stakeholder_routing(
    briefing: RiskBriefingOutput,
    chunker: ChunkPlanner,
    llm: StructuredLLM,
    output_dir: Path,
) -> StakeholderRoutingOutput:
    stage = LLMStage.STAKEHOLDER_ROUTING.value
    chunker.record_no_sections(
        stage=stage,
        input_artifacts=["risk_briefing_draft.md"],
        reason="Stakeholder routing uses structured recommended actions and team responsibility descriptions rather than source sections.",
    )
    payload = {
        "recommended_actions": model_to_jsonable(briefing.recommended_actions),
        "allowed_teams": sorted(ALLOWED_TEAMS),
        "team_responsibilities": TEAM_RESPONSIBILITIES,
    }
    result = llm.call(
        stage=stage,
        system_prompt=PROMPTS_BY_STAGE[stage],
        payload=payload,
        response_model=StakeholderRoutingOutput,
        input_artifacts=["risk_briefing_draft.md"],
        output_artifact="stakeholder_routing.json",
        section_ids_included=[],
    )
    write_json(output_dir / "stakeholder_routing.json", result)
    return result


def run_change_velocity_analysis(
    corpus: CorpusArtifact,
    semantic_diff: SemanticDiffOutput,
    chunker: ChunkPlanner,
    llm: StructuredLLM,
    settings: Settings,
    output_dir: Path,
) -> ChangeVelocityReport:
    stage = LLMStage.CHANGE_VELOCITY_ANALYSIS.value
    chunker.record_no_sections(
        stage=stage,
        input_artifacts=["semantic_diff.json", "corpus.json"],
        reason="Change velocity uses current run metadata and prior run state, not source section text.",
    )
    computed = _compute_velocity_report(corpus, semantic_diff, settings, output_dir)
    payload = {"computed_report": model_to_jsonable(computed)}
    result = llm.call(
        stage=stage,
        system_prompt=PROMPTS_BY_STAGE[stage],
        payload=payload,
        response_model=ChangeVelocityReport,
        input_artifacts=["semantic_diff.json", "corpus.json"],
        output_artifact="change_velocity_report.json",
        section_ids_included=[],
    )
    write_json(output_dir / "change_velocity_report.json", result)
    _write_run_state(corpus, output_dir / settings.run_state_file.name)
    return result


def _ensure_semantic_diff_shape(
    semantic_diff: SemanticDiffOutput,
    selected_sections: list[CorpusSection],
    jurisdiction_tags: JurisdictionTagsOutput,
) -> SemanticDiffOutput:
    if not semantic_diff.changes:
        section_ids = [section.section_id for section in selected_sections[:3]]
        semantic_diff.changes.append(
            SemanticChange(
                change_id="CHG-001",
                type="no_material_change",
                severity="none",
                before="No material semantic change identified.",
                after="No material semantic change identified.",
                affected_section_ids=section_ids,
                jurisdiction="unknown",
                risk_summary="The model returned no changes, so the pipeline emitted the required no_material_change record.",
            )
        )

    tag_map = {tag.section_id: tag.jurisdiction for tag in jurisdiction_tags.tags}
    for change in semantic_diff.changes:
        if change.jurisdiction:
            continue
        jurisdictions = {tag_map.get(section_id) for section_id in change.affected_section_ids}
        jurisdictions.discard(None)
        jurisdictions.discard("unknown")
        change.jurisdiction = jurisdictions.pop() if len(jurisdictions) == 1 else "unknown"
    return semantic_diff


def _source_section_ids_for_findings(
    semantic_diff: SemanticDiffOutput,
    contradictions: ContradictionsOutput,
) -> set[str]:
    section_ids: set[str] = set()
    for change in semantic_diff.changes:
        section_ids.update(change.affected_section_ids)
    for contradiction in contradictions.contradictions:
        section_ids.update(contradiction.source_section_ids)
    return section_ids


def _sections_payload(sections: list[CorpusSection]) -> list[dict[str, Any]]:
    return [
        {
            "document_id": section.document_id,
            "document_name": section.document_name,
            "source_url": section.source_url,
            "section_id": section.section_id,
            "section_title": section.section_title,
            "text": section.text,
            "character_count": section.character_count,
            "content_hash": section.content_hash,
        }
        for section in sections
    ]


def _compute_velocity_report(
    corpus: CorpusArtifact,
    semantic_diff: SemanticDiffOutput,
    settings: Settings,
    output_dir: Path,
) -> ChangeVelocityReport:
    current_timestamp = utc_now()
    state_path = output_dir / settings.run_state_file.name
    previous_timestamp = current_timestamp
    days_between = 0
    if state_path.exists():
        try:
            previous_state = read_json(state_path)
            previous_timestamp = str(previous_state.get("run_timestamp") or current_timestamp)
            previous_dt = _parse_timestamp(previous_timestamp)
            current_dt = _parse_timestamp(current_timestamp)
            days_between = max((current_dt - previous_dt).days, 0)
        except Exception as exc:
            logger.warning("Could not read prior run state for velocity report: {}", exc)

    material_changes = sum(
        1
        for change in semantic_diff.changes
        if change.type != "no_material_change" and change.severity != "none"
    )
    extrapolated = 0.0
    if days_between >= 1:
        extrapolated = round((material_changes / days_between) * 30, 2)

    return ChangeVelocityReport(
        current_run_timestamp=current_timestamp,
        previous_run_timestamp=previous_timestamp,
        material_changes_detected=material_changes if days_between >= 1 else 0,
        days_between_runs=days_between,
        extrapolated_material_changes_per_30_days=extrapolated,
    )


def _write_run_state(corpus: CorpusArtifact, path: Path) -> None:
    document_a_text = "\n\n".join(section.text for section in corpus.sections if section.document_id == "A")
    write_json(
        path,
        {
            "run_timestamp": utc_now(),
            "document_a_content_hash": stable_hash(document_a_text, length=32),
        },
    )


def _parse_timestamp(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


if __name__ == "__main__":
    main()
