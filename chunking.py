from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from models import ChunkingLogArtifact, ChunkingRecord, CorpusSection
from settings import Settings
from utils import utc_now


KEYWORD_PRIORITY = [
    "regulated",
    "license",
    "jurisdiction",
    "client funds",
    "segregated",
    "leverage",
    "closure",
    "responsible",
    "fraud",
    "restriction",
    "terms",
    "risk",
    "account",
]


@dataclass
class ChunkPlanner:
    settings: Settings
    records: list[ChunkingRecord] = field(default_factory=list)

    def select_sections(
        self,
        stage: str,
        sections: list[CorpusSection],
        input_artifacts: list[str],
        reason: str,
        document_ids: set[str] | None = None,
        section_ids: set[str] | None = None,
        balanced: bool = False,
    ) -> list[CorpusSection]:
        candidates = list(sections)
        if document_ids is not None:
            candidates = [section for section in candidates if section.document_id in document_ids]
        if section_ids is not None:
            candidates = [section for section in candidates if section.section_id in section_ids]
        if balanced:
            ordered = self._balanced_order(candidates)
        else:
            ordered = sorted(candidates, key=lambda section: (_priority_score(section), section.document_id, section.section_id))
        selected: list[CorpusSection] = []
        selected_ids: set[str] = set()
        included_chars = 0
        for section in ordered:
            section_cost = section.character_count
            if selected and included_chars + section_cost > self.settings.max_chars_per_llm_batch:
                continue
            if not selected and section_cost > self.settings.max_chars_per_llm_batch:
                selected.append(section)
                selected_ids.add(section.section_id)
                included_chars += section_cost
                continue
            selected.append(section)
            selected_ids.add(section.section_id)
            included_chars += section_cost

        omitted_ids = [section.section_id for section in candidates if section.section_id not in selected_ids]
        self.records.append(
            ChunkingRecord(
                stage=stage,
                batch_number=1,
                input_artifacts=input_artifacts,
                included_section_ids=[section.section_id for section in selected],
                omitted_section_ids=omitted_ids,
                selection_reason=reason,
                included_character_count=included_chars,
                max_character_budget=self.settings.max_chars_per_llm_batch,
            )
        )
        return selected

    def record_no_sections(self, stage: str, input_artifacts: list[str], reason: str) -> None:
        self.records.append(
            ChunkingRecord(
                stage=stage,
                batch_number=1,
                input_artifacts=input_artifacts,
                included_section_ids=[],
                omitted_section_ids=[],
                selection_reason=reason,
                included_character_count=0,
                max_character_budget=self.settings.max_chars_per_llm_batch,
            )
        )

    def artifact(self) -> ChunkingLogArtifact:
        return ChunkingLogArtifact(generated_at=utc_now(), records=self.records)

    def _balanced_order(self, sections: list[CorpusSection]) -> list[CorpusSection]:
        by_doc: dict[str, list[CorpusSection]] = defaultdict(list)
        for section in sections:
            by_doc[section.document_id].append(section)
        for doc_sections in by_doc.values():
            doc_sections.sort(key=lambda section: (_priority_score(section), section.section_id))
        ordered: list[CorpusSection] = []
        while any(by_doc.values()):
            for document_id in sorted(by_doc):
                if by_doc[document_id]:
                    ordered.append(by_doc[document_id].pop(0))
        return ordered


def _priority_score(section: CorpusSection) -> int:
    haystack = f"{section.section_title} {section.text}".lower()
    score = 0
    for index, keyword in enumerate(KEYWORD_PRIORITY):
        if keyword in haystack:
            score -= 100 - index
    return score
