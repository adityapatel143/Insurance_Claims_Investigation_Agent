# ADR 0003: DynamoDB for job status and idempotency

- Status: Accepted
- Date: 2026-09-30

## Context

Job status is mutable, multi-writer state (API, orchestrator, Gateway tools) that must support direct
lookup and safe concurrent transitions. SQS delivers at least once, and clients may retry `POST /claims`.

## Decision

1. **One table**, partition key `job_id` (string), no sort key. Direct `GetItem` serves the status API; the
   handler also checks that the stored `claim_id` matches the path.
2. **Submission idempotency:** the request carries a client-generated `client_request_id` (UUID).
   `job_id = uuid5(namespace, submitter_principal | claim_id | client_request_id)`.
   `PutItem` with `attribute_not_exists(job_id)`:
   - new → create `QUEUED`, send SQS message, return `202`;
   - exists with identical request hash → return the existing job (`202`); if still `QUEUED`, re-send the
     message (safe because dispatch is idempotent);
   - exists with a different request hash → `409 Conflict`.
3. **Dispatch idempotency (orchestrator):** conditional update sets `dispatch_lease_until` only when
   `status = QUEUED` and the lease is absent or expired. On successful `InvokeAgentRuntime`, a conditional
   update moves `QUEUED → PROCESSING` and sets `processing_deadline`. On failure the lease is cleared and the
   record is reported as a batch item failure. A message whose lease is held, or whose job is no longer
   `QUEUED`, is acknowledged without work.
4. **Status transitions** are enforced by condition expressions using an allowed-transition map:
   `QUEUED → PROCESSING | FAILED`, `PROCESSING → COMPLETED | REVIEW_REQUIRED | FAILED`. Terminal states are final.
5. **Stuck jobs:** if a job is `PROCESSING` past `processing_deadline`, the status handler conditionally
   transitions it to `FAILED` (category `TIMEOUT`). No sweeper process is required.
6. **Stored data:** identifiers, status, timestamps, failure category, S3 keys, summary counts, request hash,
   submitter principal ARN. Never raw documents or claim narrative.
7. TTL attribute `expires_at` (enabled for dev/sample jobs); point-in-time recovery and deletion protection in prod;
   AWS-owned encryption.

## Consequences

- Every write is a single-item conditional operation; no transactions needed.
- Job IDs are reproducible from the request, which makes client retries safe.

## Alternatives considered

- **Separate idempotency table:** unnecessary; the job record is the idempotency record.
- **Powertools idempotency utility:** adds a dependency for logic that is a few conditional writes.
