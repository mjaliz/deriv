## Executive Summary
The staged review found compliance-relevant items that should be checked against the cited sections. This mock briefing is generated from structured Stage 1 and Stage 2 outputs.

## Material Changes
- CHG-001: Current regulatory language differs semantically from the prior snapshot and needs review.

## Cross-Document Contradictions
- CON-001: These sections should be reviewed together because their obligations or customer-facing commitments may need operational alignment.
- CON-002: These sections should be reviewed together because their obligations or customer-facing commitments may need operational alignment.

## Compliance Risk Level
Medium

## Recommended Actions
```json
[
  {
    "action_id": "A1",
    "action": "Review the identified compliance findings against the cited source sections and approve any public-language updates.",
    "owner_type": "Legal",
    "priority": "P1",
    "source_finding_ids": [
      "CHG-001",
      "CON-001",
      "CON-002"
    ]
  },
  {
    "action_id": "A2",
    "action": "Assess operational impact and prepare internal handling notes for affected customer workflows.",
    "owner_type": "Risk",
    "priority": "P2",
    "source_finding_ids": [
      "CHG-001",
      "CON-001",
      "CON-002"
    ]
  }
]
```
