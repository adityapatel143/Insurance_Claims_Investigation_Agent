# Operations runbook

All commands use `ENV=dev` as an example. Find related logs by `correlation_id` or `job_id`
(CloudWatch Logs Insights: `fields @timestamp, event, status | filter correlation_id = "<id>"`).

## Alarms

| Alarm | Meaning | First actions |
|---|---|---|
| `<prefix>-queue-oldest-message-age` | Messages are not being dispatched | Check that `agent_runtime_arn` is set and the SQS trigger is enabled; check orchestrator errors and throttles; check runtime health. |
| `<prefix>-dlq-depth` | Dispatch failed after all retries | Inspect orchestrator logs for the message's `correlation_id`; fix the cause; see "Redrive" below. The job is already `FAILED`/`DISPATCH_EXHAUSTED`. |
| `<prefix>-<fn>-errors` / `-throttles` | Lambda failures or concurrency limits | Read the function's logs (`exception_type`, `event`); for throttles review reserved concurrency and account limits. |
| `<prefix>-jobs-failed` | One or more jobs ended `FAILED` | Look up the job's `failure_category` via the status API or DynamoDB; follow the matching section below. |

## Failure categories

| Category | Typical cause | Action |
|---|---|---|
| `DISPATCH_EXHAUSTED` | Runtime unavailable, IAM denial, wrong runtime ARN | Fix the cause, then ask the client to resubmit with a new `client_request_id`. |
| `TIMEOUT` | Investigation exceeded its deadline, or runtime could not reach the Gateway | Check runtime logs for `investigation_aborted` / `investigation_failed`; check Gateway and tools Lambda logs. |
| `TOOL_ERROR` | Tool rejected arguments or failed | Tools Lambda logs (`tool_call` with `error_category`). |
| `DEPENDENCY_UNAVAILABLE` | Throttling or service errors | Check service health and quotas; resubmit. |
| `RUNTIME_ERROR` | Unexpected runtime exception | Runtime logs (`exception_type`); fix and redeploy. |

`FAILED` is terminal. Recovery is a new submission (new `client_request_id`), which keeps the audit trail intact.

## Redrive from the DLQ

Redriving a message whose job is already `FAILED` is harmless (the orchestrator skips non-`QUEUED` jobs).
To retry dispatch, have the client resubmit instead. To clear the DLQ after investigation, use the SQS
console "Start DLQ redrive" or purge it deliberately.

## Deployments

- **IAM change**: `scripts/sh/tf_plan.sh dev foundation && scripts/sh/tf_apply.sh dev foundation`,
  then plan the platform stack to confirm no drift.
- **Application code (Lambda)**: `scripts/sh/tf_plan.sh dev platform && scripts/sh/tf_apply.sh dev platform`
  (the plan script rebuilds `dist/lambda.zip`).
- **Agent code**: `scripts/sh/build_image.sh <new> && scripts/sh/push_image.sh dev <new>`, set
  `agent_image_tag`, plan and apply the platform stack. Image tags are immutable; use a new tag for every build.
- **Guardrail change**: edit `modules/bedrock-guardrail`, bump `guardrail_version_description` to publish a
  new version, plan and apply (the runtime receives the new version through its environment).
- **Prompts**: part of the agent image; rebuild and push.

## Re-indexing retrieval content

```bash
scripts/sh/create_index.sh dev --recreate
scripts/sh/seed.sh dev
```

Indexing is append-only, so always recreate before reseeding. Allow up to about a minute before searches
see new chunks.

## Stuck jobs

A job in `PROCESSING` past `processing_deadline` is marked `FAILED`/`TIMEOUT` the next time its status is
read. No sweeper runs; read the status to settle it.

## Access and data requests

- Report access: only the submitting principal receives a presigned URL. Operators with S3 access
  can read `reports/` directly; such access is recorded by CloudTrail.
- Deletion requests: see [privacy-and-retention.md](privacy-and-retention.md#deletion).
