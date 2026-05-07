from __future__ import annotations

import json

from constants import REQUIRED_BRIEFING_SECTIONS
from models import HallucinationValidationOutput, RecommendedAction, RiskBriefingOutput
from utils import model_to_jsonable, normalize_text


def render_risk_briefing(briefing: RiskBriefingOutput) -> str:
    material_changes = _render_list(briefing.material_changes)
    contradictions = _render_list(briefing.cross_document_contradictions)
    actions_json = json.dumps(
        [model_to_jsonable(action) for action in briefing.recommended_actions],
        indent=2,
        ensure_ascii=False,
    )
    return (
        f"## {REQUIRED_BRIEFING_SECTIONS[0]}\n"
        f"{briefing.executive_summary.strip()}\n\n"
        f"## {REQUIRED_BRIEFING_SECTIONS[1]}\n"
        f"{material_changes}\n\n"
        f"## {REQUIRED_BRIEFING_SECTIONS[2]}\n"
        f"{contradictions}\n\n"
        f"## {REQUIRED_BRIEFING_SECTIONS[3]}\n"
        f"{briefing.compliance_risk_level}\n\n"
        f"## {REQUIRED_BRIEFING_SECTIONS[4]}\n"
        "```json\n"
        f"{actions_json}\n"
        "```\n"
    )


def apply_validation_corrections(draft: str, validation: HallucinationValidationOutput) -> str:
    final = draft
    for claim in validation.claims:
        if claim.grounded:
            continue
        claim_text = normalize_text(claim.claim)
        correction = normalize_text(claim.recommended_correction or "")
        if claim_text and claim_text in final and correction:
            final = final.replace(claim_text, correction)
        elif claim_text:
            lines = []
            for line in final.splitlines():
                if claim_text not in normalize_text(line):
                    lines.append(line)
            final = "\n".join(lines).rstrip() + "\n"
    return final


def actions_by_id(actions: list[RecommendedAction]) -> dict[str, RecommendedAction]:
    return {action.action_id: action for action in actions}


def _render_list(items: list[str]) -> str:
    if not items:
        return "- None identified."
    return "\n".join(f"- {item.strip()}" for item in items if item.strip()) or "- None identified."
