# ADR 0001: Asynchronous processing with API Gateway, DynamoDB, and SQS

- Status: Accepted
- Date: 2026-09-30

## Context

A claim investigation involves several model calls, retrieval, and document parsing. It can take minutes,
which exceeds reasonable HTTP latency and the API Gateway HTTP API integration timeout. Clients need a
stable handle to poll, and failures must be retried without duplicating work.

## Decision

1. **Synchronous edge (fast, bounded):** an API Gateway HTTP API with IAM (SigV4) authorization on every route.
   - `POST /uploads` → upload Lambda returns an S3 **presigned POST** for `intake/{claim_id}/{document_id}`.
     The POST policy enforces `content-length-range` and an exact `Content-Type` from the allowlist.
   - `POST /claims` → intake Lambda validates the body with Pydantic, `HeadObject`s each referenced object
     (size, content type, key prefix), copies mismatches to `quarantine/` and rejects the request,
     conditionally creates the job (`QUEUED`), sends one SQS message, returns `202 Accepted` with
     `job_id`, `claim_id`, `correlation_id`, and a status URL.
   - `GET /claims/{claim_id}/jobs/{job_id}` → status Lambda reads the job; a presigned report URL is
     returned only to the submitting IAM principal.
2. **Asynchronous core:** an SQS investigation queue (SQS-managed encryption, DLQ with bounded `maxReceiveCount`)
   triggers the orchestrator Lambda through an event source mapping with `ReportBatchItemFailures`.
   The orchestrator only dispatches: it leases the job, calls `InvokeAgentRuntime`, and returns.
   The investigation runs as an async task inside AgentCore Runtime (ADR 0002).
3. Queue visibility timeout ≥ 6 × orchestrator Lambda timeout.
4. On the final receive (`ApproximateReceiveCount ≥ maxReceiveCount`) the orchestrator marks the job
   `FAILED` (category `DISPATCH_EXHAUSTED`) before the message moves to the DLQ.
5. A correlation ID is created at the API edge (or accepted from a validated `X-Correlation-Id` header)
   and propagated through the job record, SQS message, runtime payload, tool calls, and logs.

## Consequences

- Clients poll for status; no long-lived connections.
- Duplicate SQS deliveries are expected and handled by idempotency (ADR 0003).
- Presigned POST (not PUT) is required because only POST policies can enforce a size range server-side.
- No S3 event notifications are needed; validation happens at `POST /claims`.

## Alternatives considered

- **Synchronous API invoking the agent:** rejected — timeouts and no retry semantics.
- **Step Functions:** viable, but adds a second orchestration layer on top of AgentCore Runtime without
  clear benefit for a single dispatch step.
- **Lambda Function URLs:** rejected in favour of one API with per-route integration and access logging.
