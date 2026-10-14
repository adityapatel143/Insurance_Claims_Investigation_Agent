# Data flow

| Step | Actor | Reads | Writes | Notes |
|---|---|---|---|---|
| 1 | Client -> `POST /uploads` | — | — | Returns a presigned POST for `intake/{claim_id}/{document_id}/{file_name}`; policy fixes `Content-Type` and `content-length-range`. |
| 2 | Client -> S3 | — | `intake/…` | Default bucket encryption (SSE-S3, AES256). |
| 3 | Client -> `POST /claims` | `intake/…` (HeadObject) | `quarantine/…` (on mismatch), `normalized/{claim}/{job}/submission.json`, DynamoDB job (`QUEUED`), SQS message | The narrative is stored only in the submission object. The job and message hold identifiers, S3 keys, and counts. |
| 4 | Orchestrator | DynamoDB job, SQS message | DynamoDB lease, `PROCESSING`, `processing_deadline` | Runtime payload: identifiers, S3 keys, hashed actor ID, deadline. |
| 5 | Runtime | `normalized/…/submission.json`, `intake/…` | `normalized/{claim}/{job}/documents/{doc}.json` | Normalized documents hold extracted fields and status, not raw text. |
| 6 | Runtime -> Gateway tools | DynamoDB job, submission, OpenSearch | — | Retrieval returns chunk text to the runtime only; chunk text is not persisted in results. |
| 7 | Runtime -> Bedrock | Prompt with fenced evidence, sources, memory context | — | Guardrail filters input and output; PII types are anonymized. |
| 8 | Runtime -> Memory | Preferences, job-scoped summaries | Job summary event (codes and counts only) | Actor is a SHA-256 hash of the caller's principal ARN. |
| 9 | Runtime -> `persist_investigation_findings` | — | `reports/{claim}/{job}/report.json`, `report.md`, DynamoDB terminal status | Status derived from the validated result. |
| 10 | Client -> `GET …/jobs/{job_id}` | DynamoDB job | DynamoDB (timeout only) | Report URL only for the submitting principal; 5-minute default expiry. |

## What each store contains

| Store | Contents | Never contains |
|---|---|---|
| S3 `intake/` | Uploaded documents | — |
| S3 `normalized/` | Submission JSON (includes narrative), extracted fields per document | — |
| S3 `reports/` | Advisory JSON and Markdown reports with evidence references | Retrieved chunk text |
| S3 `quarantine/` | Rejected uploads | — |
| S3 `sample-data/` | Synthetic guidance, historical examples, sample claims | Real data |
| DynamoDB | Job identifiers, status, timestamps, S3 keys, request hash, principal ARN, counts | Narrative, document content |
| SQS | Identifiers, S3 keys, document references | Narrative, document content |
| OpenSearch | Synthetic guidance and historical chunks with embeddings | Claim submissions |
| AgentCore Memory | Hashed actor, job-scoped summaries of codes and counts | Documents, narrative, identities |
| CloudWatch Logs | Events, identifiers, statuses, latencies, error categories | Payloads, document text, exception messages |
