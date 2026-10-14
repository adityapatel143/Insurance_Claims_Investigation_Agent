# Task: risk indicators and analyst actions

Using the evidence index, missing information, anomaly signals, and retrieved guidance, produce:

- `risk_indicators`: structured indicators, each with `category` (UPPER_SNAKE_CASE), `level`
  (`LOW`, `MEDIUM`, `HIGH`), `rationale`, `basis`, `evidence_refs`, and `confidence`.
  `basis` must be `EVIDENCE` when the cited items directly show it, `INFERENCE` when you are reasoning
  beyond what they state, and `MISSING_INFORMATION` when the indicator arises from absent information.
- `recommended_analyst_actions`: concrete next investigative steps for the analyst (for example
  "Request the itemised repair invoice"), each with `rationale`, `priority`, and `evidence_refs`.
  Actions must be investigative, never adjudicative.
- `confidence`: overall confidence (0 to 1) in the completeness of this assessment.
- `limitations`: gaps or caveats.

Levels describe how much review attention an item deserves, not whether the claim is valid.
