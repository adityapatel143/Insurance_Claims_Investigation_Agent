# Task: potential anomaly signals

Review the evidence index, the rule-based signals already detected, the synthetic guidance, and any
similar synthetic historical examples. Identify additional, explainable potential anomaly signals that
the rules did not already capture.

For each signal provide:
- `code`: UPPER_SNAKE_CASE short label (for example `DESCRIPTION_DOCUMENT_MISMATCH`);
- `description`: one or two neutral sentences describing what differs or is unusual and why it may
  require review;
- `evidence_refs`: the evidence IDs that show it;
- `confidence`: 0 to 1;
- `limitations`: what could explain the observation innocently or what is unknown;
- `origin`: always `MODEL`.

Do not repeat rule-based signals. Return an empty list when nothing further is supported by evidence.
