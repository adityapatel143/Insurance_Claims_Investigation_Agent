# Sample data (synthetic)

**Every file in this directory is synthetic.** All people, policies, vehicles, addresses, references, and
amounts are fictional. None of it is suitable for production use or for evaluating real claims.

## Contents

| Path | Purpose |
|---|---|
| `claims/complete/` | AUTO claim with claim form, repair estimate, and incident report that agree. |
| `claims/missing-documents/` | PROPERTY claim with only a claim form; the repair estimate is missing. |
| `claims/inconsistent/` | TRAVEL claim whose invoice total and incident date differ from the claim form, reported 53 days after the incident. |
| `guidance/` | Synthetic investigation guidance indexed as `GUIDANCE` (`claim_type: GENERAL` applies to all types). |
| `historical/` | Synthetic historical examples indexed as `HISTORICAL_CLAIM`. |

Each `claims/<scenario>/claim.json` is a submission template: `scripts/submit_sample_claim.py` uploads the
listed files through the API, generates a unique `claim_id` from `claim_id_prefix`, and submits the claim.

Guidance and historical files start with a small front-matter block (`title`, `claim_type`,
`source_type`) that `scripts/seed_sample_data.py` uses when chunking and indexing.

## Expected advisory outcomes

These are the deterministic signals the code is designed to raise; model output may add further
potential anomaly signals. Every outcome is advisory and requires analyst review.

| Scenario | Deterministic signals | Expected status |
|---|---|---|
| complete | none | `COMPLETED` if the model reports confidence at or above the threshold and no elevated risk; otherwise `REVIEW_REQUIRED` |
| missing-documents | missing repair estimate | `REVIEW_REQUIRED` (`MISSING_INFORMATION`) |
| inconsistent | `AMOUNT_MISMATCH`, `INCIDENT_DATE_MISMATCH`, `LATE_REPORTING` | `REVIEW_REQUIRED` |
