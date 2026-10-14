# Privacy and retention

## Principles

- **Synthetic only outside production.** Sample data and fixtures are fictional; do not load real claims
  into `dev`.
- **Minimise copies.** Claim content lives only in S3. Queues, job records, logs, and memory hold
  identifiers, keys, statuses, and counts.
- **No sensitive inference.** The system does not infer protected attributes or diagnose conditions; the
  guardrail denies those topics and anonymizes common PII types in model traffic.

## Retention by store

| Store | dev | prod | Mechanism |
|---|---|---|---|
| S3 `intake/` | 14 days | 90 days | Lifecycle expiration |
| S3 `normalized/` | 14 days | 90 days | Lifecycle expiration |
| S3 `reports/` | 30 days | 365 days | Lifecycle expiration |
| S3 `quarantine/` | 7 days | 30 days | Lifecycle expiration |
| S3 noncurrent versions | 30 days | 30 days | Lifecycle noncurrent expiration |
| DynamoDB jobs | 30 days (TTL) | No TTL; PITR enabled | `expires_at` attribute |
| AgentCore Memory events | 7 days | 30 days | `event_expiry_duration` |
| CloudWatch Logs | 14 days | 365 days | Log group retention |
| SQS | 4 days (main), 14 days (DLQ) | same | Message retention |

Values come from `infra/environments/<env>/{foundation,platform}/locals.tf` and module defaults; change them there.
Long-term memory records extracted by AgentCore strategies follow the service's own lifecycle; delete them
explicitly when required (below).

## AgentCore Memory

- `actorId` is the SHA-256 hash of the submitting principal ARN; `sessionId` is `claims-job-{job_id}`.
- Stored: one summary per job made of status, confidence, signal codes, risk categories and levels,
  review reasons, and counts. Never documents, narratives, names, or government identifiers.
- Reads are limited to the actor's preferences and the current job's summaries.

## Deletion

| Request | Steps |
|---|---|
| A claim's data | Delete `intake/{claim_id}/`, `normalized/{claim_id}/`, `reports/{claim_id}/`, and `quarantine/{claim_id}/` (all versions); delete the claim's job items in DynamoDB; delete memory records for the job's session (`/claims/summaries/{actorId}/claims-job-{job_id}`) through the AgentCore Memory APIs. |
| An investigator's memory | Delete memory records in `/claims/preferences/{actorId}` and their summaries. |
| An environment | `terraform destroy` (see README cleanup); the bootstrap state bucket is retained separately. |

Point-in-time recovery backups (prod) and S3 noncurrent versions keep data until their windows expire;
account for them in deletion commitments.
