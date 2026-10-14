# Threat model

Scope: the deployed stack in one AWS account and Region. Method: STRIDE per trust boundary
(see [architecture-diagram.md](architecture-diagram.md#trust-boundaries)). Residual risks are listed for
review before any production use with real data.

## Assets

Claim documents and narratives; investigation reports; job records; IAM roles; model and
guardrail configuration; the integrity of human-review routing.

## Threats and mitigations

| ID | Category | Threat | Mitigations | Residual risk |
|---|---|---|---|---|
| T1 | Spoofing | Unauthenticated API calls | `AWS_IAM` on every route; callers need `execute-api:Invoke` | Over-broad caller policies; scope them to route ARNs |
| T2 | Spoofing | Caller reads another caller's report | Status lookup scoped to `claim_id`; report URL only for the submitting principal ARN | Same principal shared across people |
| T3 | Tampering | Uploading oversized or disguised files | POST policy enforces type and size; intake re-checks `HeadObject`, quarantines mismatches; only text formats are parsed | Malicious content inside allowed text formats (no malware scan) |
| T4 | Tampering | Prompt injection in documents or retrieved text | Untrusted-data fencing; fence-tag stripping; injection markers force review; model has no tools; output schema and grounding validation; Bedrock prompt-attack filter | Novel injections that evade markers may still bias narrative text, which remains advisory and reviewed |
| T5 | Tampering | Model output asserts a decision or fraud label | Prohibited-wording validation; denied topics in the guardrail; fixed advisory notice | Paraphrases outside the patterns; analyst review is the final control |
| T6 | Tampering | Forcing `COMPLETED` despite issues | Routing is deterministic; tools Lambda re-derives review reasons and rejects inconsistent results; `update_job_status` cannot set terminal success | Reasons not derivable from the result (guardrail flags) rely on runtime code integrity |
| T7 | Repudiation | Disputed status changes or tool calls | Conditional transitions with timestamps; structured logs for every transition and tool call with correlation ID; API access logs; CloudTrail | Log retention is environment-configured |
| T8 | Information disclosure | Claim content in logs, queues, memory | Content kept in S3 only; log redaction; exception messages not logged; memory summaries are codes and counts | Developers adding new log fields; review in code review |
| T9 | Information disclosure | Public data exposure | Data bucket public access block; AOSS IAM-only data access; no anonymous application endpoints | No explicit bucket/queue TLS deny policies; AOSS public network endpoint by default (IAM-authenticated); use the VPC endpoint option for stricter setups |
| T10 | Information disclosure | PII reaching the model | Guardrail PII anonymization for common types | Free-text PII outside supported entity types |
| T11 | Denial of service | API flooding | API throttling; Lambda concurrency; SQS buffering; orchestrator max concurrency | Account-level quotas; consider AWS WAF if exposed broadly |
| T12 | Denial of service | Poison messages | Partial batch failures; bounded receives; DLQ; job marked `FAILED` | DLQ requires operator action |
| T13 | Elevation of privilege | Tool misuse | Five narrowly scoped tools; strict argument models; job, claim, correlation, and status checks; gateway role can invoke only the tools Lambda | Compromise of the runtime role still allows reading `intake/` and `normalized/` |
| T14 | Elevation of privilege | Over-permissive IAM | Separate workload roles and service trust policies | Every workload role has account-wide `AdministratorAccess` for learning; compromise can read, modify, or delete resources across the account. Never use with real data or shared accounts. |
| T15 | Supply chain | Vulnerable dependencies or base image | Locked `uv.lock`; pinned provider and lock files; ECR scan on push; immutable tags; Bandit and secret scanning in CI | Base image pinned by tag, not digest |
| T16 | Spoofing / disclosure | Optional web app served from a public, HTTP-only S3 website; pasted credentials captured by a modified page | No third-party scripts; CSP (`script-src 'self'`, `connect-src 'self' https:`); credentials held in memory only, never stored; HTTP warning banner; CORS limited to listed origins; DOM rendering via `textContent` only | Network attacker on HTTP can alter the page: use short-lived credentials scoped to `execute-api:Invoke`, trusted networks, or add CloudFront + HTTPS |

## Assumptions

- AWS account administration, CloudTrail, and IAM Identity Center are managed outside this repository.
- Non-production environments hold synthetic data only.
- Analysts are trained that every output is advisory.
