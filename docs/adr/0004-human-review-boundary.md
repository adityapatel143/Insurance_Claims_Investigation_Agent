# ADR 0004: Human-review boundary

- Status: Accepted
- Date: 2026-09-30

## Context

Model output can be wrong, ungrounded, or manipulated by content in claim documents. Claim decisions are
consequential for claimants. The system must assist analysts, never replace them.

## Decision

1. **Advisory only.** The system never approves, rejects, prices, pays, or decides eligibility. No tool or
   IAM permission exists that could perform such an action. Every report carries an advisory notice.
2. **Deterministic routing, not model discretion.** `services/human_review.py` sets
   `human_review_required = true` (final status `REVIEW_REQUIRED`) when any of the following holds:
   - any anomaly signal is present;
   - any risk indicator is `medium` or `high`;
   - overall confidence is below a configurable threshold;
   - required information is missing or evidence is inconsistent;
   - a guardrail intervened on input or output;
   - model output failed Pydantic validation after bounded retries;
   - a finding lacks at least one evidence reference, or cites a source that was not retrieved;
   - retrieval returned no guidance for the claim type.
   Otherwise the status is `COMPLETED`, which means "investigation report ready", not "claim approved".
3. **Language.** Signals use "potential anomaly signal" / "requires review". Prompts forbid fraud labels,
   protected-attribute inference, and medical diagnosis; output validation rejects banned phrases.
4. **Grounding.** Findings must reference evidence IDs from the claim's normalized documents or retrieved
   source chunk IDs. Unreferenced findings are dropped and recorded as limitations.
5. **Prompt injection.** Document and retrieved text is passed as delimited, untrusted data; instructions
   inside it are ignored by policy and never change tool scope.

## Consequences

- Many jobs will end in `REVIEW_REQUIRED`; this is intended.
- Routing rules are unit-testable without a model.

## Alternatives considered

- **Model-decided review flag:** rejected — the model cannot be trusted to judge its own reliability.
