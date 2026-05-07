## BUILD

Build a replayable multi-document compliance diff engine that ingests public policy and compliance pages, cleans and segments them, compares a prior snapshot against the current version, detects cross-document contradictions, generates a structured risk briefing, validates claims against source text, and routes findings to internal teams.

This is not a one-shot compliance summary task. The evaluator will run your pipeline from a clean checkout, may replace source URLs or snapshots with equivalent fixtures, and will verify that ingestion, semantic diffing, contradiction detection, briefing generation, validation, and routing are staged and auditable.

The pipeline must preserve intermediate artifacts, use section-level source metadata, log LLM calls, handle chunking explicitly, and ensure final briefing claims are traceable to source documents.

---

## INPUT FILES

Your pipeline must read these files from disk:

- `sources.json`
- `previous_snapshot_document_a.txt`

The sample sources and snapshot below are provided for local testing. The evaluator may replace them with equivalent source documents and snapshots.

---

## SAMPLE `sources.json`

```json
{
  "documents": [
    {
      "document_id": "A",
      "name": "Regulatory",
      "url": "https://deriv.com/regulatory/"
    },
    {
      "document_id": "B",
      "name": "Terms and Conditions - Clients",
      "url": "https://deriv.com/terms-and-conditions#clients"
    },
    {
      "document_id": "C",
      "name": "Responsible Trading",
      "url": "https://deriv.com/responsible"
    },
    {
      "document_id": "D",
      "name": "Fraud Prevention",
      "url": "https://deriv.com/fraud-prevention"
    }
  ]
}
```

---

## SAMPLE `previous_snapshot_document_a.txt`

```text
Deriv is licensed and regulated by the British Virgin Islands Financial Services Commission (FSC) under the Securities and Investment Business Act, 2010. Deriv (Europe) Limited is licensed by the Malta Financial Services Authority (MFSA). Deriv (FX) Ltd is also regulated under the FSC BVI. Client funds are held in segregated accounts. Leverage available to retail clients in the EU is limited to 1:30 for major currency pairs in accordance with ESMA guidelines. A cooling-off period of 24 hours applies to all account closures requested within the first 7 days of registration.
```

---

## CONTROLLED VOCABULARIES

Define these vocabularies in code and validate LLM outputs against them.

Allowed change types:

```text
addition
removal
modification
clarification
no_material_change
```

Allowed severities:

```text
critical
major
minor
none
```

Allowed compliance risk levels:

```text
Low
Medium
High
```

Allowed internal teams:

```text
Legal
Risk
Product
Marketing
Engineering
Customer Support
```

Allowed action priorities:

```text
P0
P1
P2
P3
```

---

## PIPELINE STAGES

Your implementation must enforce these stages in code:

```text
INIT
 -> SOURCES_LOADED
 -> LIVE_DOCUMENTS_FETCHED
 -> DOCUMENTS_CLEANED
 -> DOCUMENTS_SEGMENTED
 -> SNAPSHOT_DIFF_COMPLETE
 -> CROSS_DOCUMENT_CHECK_COMPLETE
 -> RISK_BRIEFING_DRAFTED
 -> HALLUCINATION_VALIDATED, if attempted
 -> FINAL_BRIEFING_WRITTEN
 -> STAKEHOLDER_ROUTING_COMPLETE
 -> AUDIT_LOG_EXPORTED
 -> VALIDATION_COMPLETE
 -> RESULTS_FINALISED
```

Final routing and briefing outputs must not be produced before document ingestion, segmentation, Stage 1 semantic diff, Stage 2 contradiction detection, and Stage 3 briefing generation have completed.

If hallucination validation is attempted, final briefing must reflect any corrections.

---

## MUST COMPLETE

### 1. Document Ingestion and Cleaning

Fetch and process all configured live pages.

JavaScript-rendered pages must be handled using Playwright or an equivalent browser automation tool.

For each page:

- scrape page content
- remove navigation, footers, cookie banners, scripts, and UI chrome
- preserve meaningful headings and body text
- segment into logical sections by heading or paragraph grouping
- assign stable section IDs

Save the cleaned corpus to `corpus.json`.

Each section must include:

```json
{
  "document_id": "A",
  "document_name": "Regulatory",
  "source_url": "https://deriv.com/regulatory/",
  "section_id": "A-001",
  "section_title": "string",
  "text": "string",
  "character_count": 0,
  "content_hash": "string"
}
```

Do not silently drop documents that fail to load. Log fetch or parsing failures.

---

### 2. Context Window Chunking Strategy

Implement a chunking strategy before LLM calls.

The pipeline must not blindly send entire documents if they exceed the model context window.

For each LLM stage, record:

- which sections were included
- why they were selected
- whether any sections were omitted
- chunk or batch number, if applicable

Save this metadata to `chunking_log.json`.

---

### 3. Snapshot Semantic Diff

Make a Stage 1 LLM call comparing:

- `previous_snapshot_document_a.txt`
- the cleaned current live version of Document A
- relevant section metadata

The task is semantic diffing.

The model must compare meaning, obligation, scope, regulatory position, jurisdictional applicability, and user-facing commitment. It must not perform only character-level or wording-level diffing.

Each change must include:

```json
{
  "change_id": "string",
  "type": "addition | removal | modification | clarification | no_material_change",
  "severity": "critical | major | minor | none",
  "before": "string",
  "after": "string",
  "affected_section_ids": ["A-001"],
  "jurisdiction": "string | null",
  "risk_summary": "string"
}
```

If no material change is detected, the model must output one `no_material_change` record explaining why.

Save output to `semantic_diff.json`.

---

### 4. Cross-Document Contradiction Detection

Make a separate Stage 2 LLM call.

This call must receive selected sections from all four live documents simultaneously, with section IDs and source URLs.

Ask the model to identify statements that appear inconsistent, contradictory, or operationally tense across documents.

Each finding must include:

```json
{
  "contradiction_id": "string",
  "documents_involved": ["B", "C"],
  "source_section_ids": ["B-004", "C-002"],
  "statement_a": "string",
  "statement_b": "string",
  "why_it_may_conflict": "string",
  "severity": "critical | major | minor",
  "confidence": "low | medium | high"
}
```

For the public fixture, at least 2 candidate contradictions should be identified if supported by the fetched content.

If fewer than 2 are found, the output must explain why.

Save output to `contradictions.json`.

---

### 5. Risk Briefing Generation

Make a separate Stage 3 LLM call.

This call must include:

- Stage 1 semantic diff output
- Stage 2 contradiction output
- relevant source section IDs
- controlled severity and risk-level vocabularies

Generate `risk_briefing_draft.md` with these exact sections:

- Executive Summary
- Material Changes
- Cross-Document Contradictions
- Compliance Risk Level
- Recommended Actions

Recommended actions must include:

```json
{
  "action": "string",
  "owner_type": "Legal | Risk | Product | Marketing | Engineering | Customer Support",
  "priority": "P0 | P1 | P2 | P3",
  "source_finding_ids": ["change_id_or_contradiction_id"]
}
```

The briefing must not introduce claims that are not supported by Stage 1, Stage 2, or cited source sections.

---

### 6. Stakeholder Routing

Make a separate Stage 4 LLM call.

This call must include:

- recommended actions from the risk briefing
- source finding IDs
- allowed internal teams
- short team responsibility descriptions

Map each action to one or more internal teams.

For each team receiving at least one action, produce:

```json
{
  "team": "Legal",
  "action_ids": ["A1"],
  "notification": "string"
}
```

Notifications must be tailored to the team's concerns and written as realistic internal messages.

Save output to `stakeholder_routing.json`.

---

## SHOULD ATTEMPT

### 7. Hallucination Validation

After generating the draft briefing, make a separate validation LLM call.

This call must include:

- `risk_briefing_draft.md`
- `semantic_diff.json`
- `contradictions.json`
- the relevant source sections from `corpus.json`

Ask the model to identify every factual claim in the briefing and trace it to source evidence.

Each validation result must include:

```json
{
  "claim": "string",
  "grounded": true,
  "source_section_ids": ["A-001"],
  "issue": "string | null",
  "recommended_correction": "string | null"
}
```

Any ungrounded claim must be removed or corrected before writing `risk_briefing.md`.

Save validation output to `hallucination_validation.json`.

---

### 8. Audit Log

Save a machine-readable `audit_log.json`.

It must include every:

- semantic change
- contradiction
- recommended action
- routing decision
- hallucination validation correction, if attempted

Each item must include source section IDs and derived artifact references.

---

## STRETCH

### 9. Regulatory Jurisdiction Tagging

For each section of Document A, tag the likely jurisdiction.

Allowed examples:

```text
EU
BVI
Malta
global
unknown
```

Save output to `jurisdiction_tags.json`.

If a Stage 1 material change affects a specific jurisdiction, include that jurisdiction in `semantic_diff.json`.

---

### 10. Change Velocity Report

If the pipeline is run again after 24 or more hours, compare the new live snapshot against the previous stored snapshot.

Output:

```json
{
  "current_run_timestamp": "ISO-8601 timestamp",
  "previous_run_timestamp": "ISO-8601 timestamp",
  "material_changes_detected": 0,
  "days_between_runs": 0,
  "extrapolated_material_changes_per_30_days": 0.0
}
```

Save output to `change_velocity_report.json`.

---

## REQUIRED ARTIFACTS

Your repository must produce:

- `sources.json`
- `previous_snapshot_document_a.txt`
- `corpus.json`
- `chunking_log.json`
- `semantic_diff.json`
- `contradictions.json`
- `risk_briefing_draft.md`
- `risk_briefing.md`
- `stakeholder_routing.json`
- `audit_log.json`, if attempted
- `hallucination_validation.json`, if attempted
- `jurisdiction_tags.json`, if attempted
- `change_velocity_report.json`, if attempted
- `llm_calls.jsonl`

---

## `llm_calls.jsonl` REQUIREMENTS

Log one JSON object per LLM call.

Each record must include:

```json
{
  "stage": "string",
  "timestamp": "ISO-8601 timestamp",
  "provider": "string",
  "model": "string",
  "prompt_hash": "string",
  "input_artifacts": ["path"],
  "output_artifact": "path",
  "section_ids_included": ["A-001"]
}
```

There must be separate records for:

- Stage 1 semantic diff
- Stage 2 cross-document contradiction detection
- Stage 3 risk briefing generation
- Stage 4 stakeholder routing
- hallucination validation, if attempted
- jurisdiction tagging, if attempted
- change velocity analysis, if attempted

---

## VALIDATION REQUIREMENTS

The repository must include a validation command, for example:

```bash
make validate
```

or:

```bash
python validate.py
```

The validation command must check that:

- required artifacts exist
- JSON files are valid
- all configured source documents were fetched or failures were logged
- `corpus.json` contains section-level metadata
- chunking metadata exists for LLM stages
- each LLM stage is logged as a separate call
- Stage 3 uses structured outputs from Stages 1 and 2
- Stage 4 uses recommended actions from Stage 3
- controlled vocabularies are respected
- final briefing contains all required sections
- stakeholder notifications are not identical boilerplate
- audit log traces findings to source sections, if attempted
- hallucination validation corrections are applied to the final briefing, if attempted

---

## EXECUTION REQUIREMENTS

The evaluator will run the pipeline from a clean checkout.

Generated artifacts may be deleted before evaluation.

The evaluator may replace `sources.json` and `previous_snapshot_document_a.txt` with equivalent inputs.

Static precomputed outputs are not sufficient.

The solution must actually run the staged pipeline and regenerate required artifacts.

---

## TOOLS

Python or TypeScript may be used.

Any LLM provider or AI tooling may be used.

Use Playwright or an equivalent browser automation tool for JavaScript-rendered pages.

---

## TECHNICAL CONSTRAINTS

- Read source configuration and snapshot from disk.
- Scrape and clean all configured documents.
- Handle JavaScript-rendered pages.
- Do not silently truncate documents.
- Use an explicit chunking strategy for LLM context windows.
- Each LLM pipeline stage must be a separate API call.
- Stage 3 must consume structured outputs from Stages 1 and 2.
- Stage 4 must consume recommended actions from Stage 3.
- Final briefing claims should be traceable to source sections.
- Public regulatory/compliance analysis must be framed as internal review support, not legal advice.