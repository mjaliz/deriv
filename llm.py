from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeVar

from loguru import logger
from pydantic import BaseModel

from constants import LLMStage
from models import (
    ChangeVelocityReport,
    ClaimValidation,
    ContradictionFinding,
    ContradictionsOutput,
    HallucinationValidationOutput,
    JurisdictionTag,
    JurisdictionTagsOutput,
    LLMCallRecord,
    RecommendedAction,
    RiskBriefingOutput,
    SemanticChange,
    SemanticDiffOutput,
    StakeholderRoute,
    StakeholderRoutingOutput,
)
from settings import Settings
from utils import append_jsonl, first_sentence, model_to_jsonable, normalize_text, prompt_hash, utc_now


T = TypeVar("T", bound=BaseModel)


class StructuredLLM:
    def __init__(self, settings: Settings, llm_log_path: Path) -> None:
        self.settings = settings
        self.llm_log_path = llm_log_path
        self._client = None
        if not settings.mock_llm:
            if not settings.api_key_value:
                raise RuntimeError(
                    "OPENAI_API_KEY is required for real LLM calls. "
                    "Use --mock-llm only for local dry runs."
                )
            from openai import OpenAI

            self._client = OpenAI(api_key=settings.api_key_value)

    def call(
        self,
        *,
        stage: str,
        system_prompt: str,
        payload: dict[str, Any],
        response_model: type[T],
        input_artifacts: list[str],
        output_artifact: str,
        section_ids_included: list[str],
    ) -> T:
        logger.info("LLM stage {} -> {}", stage, output_artifact)
        if self.settings.mock_llm:
            parsed = mock_response(stage, payload, response_model)
            provider = "mock"
            model = "mock-structured"
        else:
            assert self._client is not None
            response = self._client.responses.parse(
                model=self.settings.openai_model,
                input=[
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {
                        "role": "user",
                        "content": json.dumps(payload, ensure_ascii=False, indent=2),
                    },
                ],
                text_format=response_model,
            )
            parsed = response.output_parsed
            provider = self.settings.openai_provider
            model = self.settings.openai_model

        result = response_model.model_validate(model_to_jsonable(parsed))
        append_jsonl(
            self.llm_log_path,
            LLMCallRecord(
                stage=stage,
                timestamp=utc_now(),
                provider=provider,
                model=model,
                prompt_hash=prompt_hash(system_prompt, payload),
                input_artifacts=input_artifacts,
                output_artifact=output_artifact,
                section_ids_included=section_ids_included,
            ),
        )
        return result


def mock_response(stage: str, payload: dict[str, Any], response_model: type[T]) -> T:
    if response_model is SemanticDiffOutput:
        return response_model.model_validate(_mock_semantic_diff(payload))
    if response_model is ContradictionsOutput:
        return response_model.model_validate(_mock_contradictions(payload))
    if response_model is RiskBriefingOutput:
        return response_model.model_validate(_mock_risk_briefing(payload))
    if response_model is HallucinationValidationOutput:
        return response_model.model_validate(_mock_hallucination_validation(payload))
    if response_model is StakeholderRoutingOutput:
        return response_model.model_validate(_mock_routing(payload))
    if response_model is JurisdictionTagsOutput:
        return response_model.model_validate(_mock_jurisdictions(payload))
    if response_model is ChangeVelocityReport:
        return response_model.model_validate(payload["computed_report"])
    raise ValueError(f"No mock response is configured for {stage}")


def _mock_semantic_diff(payload: dict[str, Any]) -> dict[str, Any]:
    previous = normalize_text(payload.get("previous_snapshot", ""))
    sections = payload.get("current_sections", [])
    current = normalize_text(" ".join(section.get("text", "") for section in sections))
    affected_ids = [section.get("section_id") for section in sections[:3] if section.get("section_id")]
    if not current or previous[:300] == current[:300]:
        return {
            "changes": [
                {
                    "change_id": "CHG-001",
                    "type": "no_material_change",
                    "severity": "none",
                    "before": first_sentence(previous) or "No prior snapshot text supplied.",
                    "after": first_sentence(current) or "No current Document A text available.",
                    "affected_section_ids": affected_ids,
                    "jurisdiction": "unknown",
                    "risk_summary": "The mock analyzer did not identify a material semantic change.",
                }
            ]
        }
    return {
        "changes": [
            {
                "change_id": "CHG-001",
                "type": "modification",
                "severity": "minor",
                "before": first_sentence(previous) or "No prior snapshot text supplied.",
                "after": first_sentence(current) or "No current Document A text available.",
                "affected_section_ids": affected_ids,
                "jurisdiction": _infer_jurisdiction(current),
                "risk_summary": "Current regulatory language differs semantically from the prior snapshot and needs review.",
            }
        ]
    }


def _mock_contradictions(payload: dict[str, Any]) -> dict[str, Any]:
    sections = payload.get("sections", [])
    by_doc: dict[str, list[dict[str, Any]]] = {}
    for section in sections:
        by_doc.setdefault(section.get("document_id", "unknown"), []).append(section)

    findings: list[dict[str, Any]] = []
    doc_pairs = [("B", "C"), ("B", "D"), ("A", "B"), ("C", "D")]
    for pair_index, (left_doc, right_doc) in enumerate(doc_pairs, start=1):
        if left_doc not in by_doc or right_doc not in by_doc:
            continue
        left = by_doc[left_doc][0]
        right = by_doc[right_doc][0]
        findings.append(
            {
                "contradiction_id": f"CON-{pair_index:03d}",
                "documents_involved": [left_doc, right_doc],
                "source_section_ids": [left["section_id"], right["section_id"]],
                "statement_a": first_sentence(left.get("text", "")),
                "statement_b": first_sentence(right.get("text", "")),
                "why_it_may_conflict": (
                    "These sections should be reviewed together because their obligations or customer-facing "
                    "commitments may need operational alignment."
                ),
                "severity": "minor",
                "confidence": "low",
            }
        )
        if len(findings) >= 2:
            break

    return {
        "contradictions": findings,
        "explanation_if_fewer_than_two": None
        if len(findings) >= 2
        else "Fewer than two candidate contradictions were available in mock mode because the selected corpus lacked enough cross-document sections.",
    }


def _mock_risk_briefing(payload: dict[str, Any]) -> dict[str, Any]:
    semantic_diff = payload.get("semantic_diff", {})
    contradictions = payload.get("contradictions", {})
    changes = semantic_diff.get("changes", [])
    contradiction_items = contradictions.get("contradictions", [])
    material = [
        f"{change.get('change_id')}: {change.get('risk_summary')}"
        for change in changes
        if change.get("type") != "no_material_change"
    ]
    if not material and changes:
        material = [f"{changes[0].get('change_id')}: No material semantic change identified."]
    contradiction_summaries = [
        f"{item.get('contradiction_id')}: {item.get('why_it_may_conflict')}" for item in contradiction_items
    ]
    finding_ids = [change.get("change_id") for change in changes if change.get("change_id")]
    finding_ids.extend(item.get("contradiction_id") for item in contradiction_items if item.get("contradiction_id"))
    actions = []
    if finding_ids:
        actions.append(
            {
                "action_id": "A1",
                "action": "Review the identified compliance findings against the cited source sections and approve any public-language updates.",
                "owner_type": "Legal",
                "priority": "P1",
                "source_finding_ids": finding_ids,
            }
        )
        actions.append(
            {
                "action_id": "A2",
                "action": "Assess operational impact and prepare internal handling notes for affected customer workflows.",
                "owner_type": "Risk",
                "priority": "P2",
                "source_finding_ids": finding_ids,
            }
        )
    return {
        "executive_summary": (
            "The staged review found compliance-relevant items that should be checked against the cited sections. "
            "This mock briefing is generated from structured Stage 1 and Stage 2 outputs."
        ),
        "material_changes": material,
        "cross_document_contradictions": contradiction_summaries,
        "compliance_risk_level": _mock_risk_level(changes, contradiction_items),
        "recommended_actions": actions,
    }


def _mock_hallucination_validation(payload: dict[str, Any]) -> dict[str, Any]:
    source_ids = payload.get("source_section_ids", [])
    return {
        "claims": [
            {
                "claim": "The draft briefing is based on Stage 1 and Stage 2 outputs.",
                "grounded": True,
                "source_section_ids": source_ids[:3],
                "issue": None,
                "recommended_correction": None,
            }
        ]
    }


def _mock_routing(payload: dict[str, Any]) -> dict[str, Any]:
    actions = payload.get("recommended_actions", [])
    by_team: dict[str, list[str]] = {}
    for action in actions:
        by_team.setdefault(action.get("owner_type", "Legal"), []).append(action.get("action_id", "A1"))
    routes = []
    for team, action_ids in sorted(by_team.items()):
        routes.append(
            {
                "team": team,
                "action_ids": action_ids,
                "notification": (
                    f"{team}: Please review action(s) {', '.join(action_ids)} with the cited finding IDs "
                    "and confirm ownership for remediation."
                ),
            }
        )
    return {"routes": routes}


def _mock_jurisdictions(payload: dict[str, Any]) -> dict[str, Any]:
    tags = []
    for section in payload.get("sections", []):
        text = f"{section.get('section_title', '')} {section.get('text', '')}"
        tags.append(
            {
                "section_id": section.get("section_id"),
                "jurisdiction": _infer_jurisdiction(text),
                "rationale": "Keyword-based mock jurisdiction tag.",
            }
        )
    return {"tags": tags}


def _mock_risk_level(changes: list[dict[str, Any]], contradictions: list[dict[str, Any]]) -> str:
    severities = [item.get("severity") for item in changes + contradictions]
    if "critical" in severities or "major" in severities:
        return "High"
    if "minor" in severities:
        return "Medium"
    return "Low"


def _infer_jurisdiction(text: str) -> str:
    lowered = text.lower()
    if "malta" in lowered or "mfsa" in lowered:
        return "Malta"
    if "bvi" in lowered or "british virgin" in lowered:
        return "BVI"
    if "eu" in lowered or "esma" in lowered or "europe" in lowered:
        return "EU"
    if "global" in lowered or "all clients" in lowered:
        return "global"
    return "unknown"


SEMANTIC_DIFF_PROMPT = """
You are a compliance analyst. Compare the prior snapshot of Document A with the current live Document A sections.
Identify semantic changes in meaning, obligation, scope, regulatory position, jurisdictional applicability, and user-facing commitment.
Use only the controlled vocabularies supplied in the payload. If no material change exists, output exactly one no_material_change record.
Every finding must cite affected section IDs.
"""

CONTRADICTION_PROMPT = """
You are a compliance analyst. Review the selected sections from all live documents simultaneously.
Identify statements that appear inconsistent, contradictory, or operationally tense across documents.
Only cite section IDs present in the payload. If fewer than two candidate contradictions are supported, explain why.
"""

RISK_BRIEFING_PROMPT = """
You generate concise internal compliance risk briefings from structured source findings.
Use only Stage 1 semantic diff findings, Stage 2 contradiction findings, and cited source sections.
Do not introduce unsupported facts. Recommended actions must use the allowed teams and priorities.
"""

HALLUCINATION_VALIDATION_PROMPT = """
You validate a compliance briefing against its source artifacts.
Identify every factual claim, mark whether it is grounded, cite source section IDs, and recommend corrections for unsupported claims.
"""

STAKEHOLDER_ROUTING_PROMPT = """
You route recommended compliance actions to internal teams.
Use only the allowed team list and responsibility descriptions. Notifications must be realistic and tailored to the recipient team.
"""

JURISDICTION_TAGGING_PROMPT = """
Tag each Document A section with the most likely jurisdiction from the allowed values: EU, BVI, Malta, global, unknown.
Use source text only and provide a short rationale for each tag.
"""

CHANGE_VELOCITY_PROMPT = """
Return the computed change velocity report exactly as a structured object.
Do not add interpretation or modify the supplied numeric values.
"""


PROMPTS_BY_STAGE = {
    LLMStage.SEMANTIC_DIFF.value: SEMANTIC_DIFF_PROMPT,
    LLMStage.CONTRADICTIONS.value: CONTRADICTION_PROMPT,
    LLMStage.RISK_BRIEFING.value: RISK_BRIEFING_PROMPT,
    LLMStage.HALLUCINATION_VALIDATION.value: HALLUCINATION_VALIDATION_PROMPT,
    LLMStage.STAKEHOLDER_ROUTING.value: STAKEHOLDER_ROUTING_PROMPT,
    LLMStage.JURISDICTION_TAGGING.value: JURISDICTION_TAGGING_PROMPT,
    LLMStage.CHANGE_VELOCITY_ANALYSIS.value: CHANGE_VELOCITY_PROMPT,
}
