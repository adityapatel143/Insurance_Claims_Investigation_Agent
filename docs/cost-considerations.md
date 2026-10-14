# Cost considerations

This document lists cost drivers; it does not quote prices. Check current AWS pricing for your Region
before deploying, and delete `dev` stacks when idle.

| Service | Driver | Levers in this repository |
|---|---|---|
| OpenSearch Serverless | Compute capacity units for indexing and search, plus storage. Collections may keep a minimum capacity while idle depending on collection generation and configuration; standby replicas add capacity. | `opensearch_standby_replicas` (off in dev); destroy dev when unused. |
| Amazon Bedrock (text model) | Input and output tokens: three structured calls per investigation plus structured-output retries | `CLAIMS_MAX_OUTPUT_RETRIES`, document size limit (`CLAIMS_MAX_DOCUMENT_BYTES`), model choice |
| Bedrock Guardrails | Text units evaluated on model input and output | Guardrail policies enabled; prompt size |
| Bedrock embeddings | One embedding per retrieval query and per indexed chunk | `retrieval_top_k`, chunk size in `seed_sample_data.py` |
| AgentCore Runtime | Session compute while investigations run | `investigation_timeout_seconds`, idle session timeout |
| AgentCore Gateway and Memory | Tool invocations; memory events and records | Five tool calls per job; summaries only |
| Lambda | Invocations and duration (arm64) | Memory sizes in `modules/platform` |
| SQS, DynamoDB (on-demand), API Gateway | Requests | — |
| S3 | Storage and requests | Lifecycle expiry per prefix (`*_retention_days`) |
| CloudWatch | Log ingestion and retention, custom metrics, alarms, dashboard | `log_retention_days`; logs exclude payloads |
| ECR | Image storage | Lifecycle keeps the latest 20 images |

## Practical guidance

- Keep `dev` short-lived; `terraform destroy` removes the collection, which is usually the largest idle cost.
- Prefer smaller, cheaper models for development; set `model_id` per environment.
- Watch `ModelStepDegraded` and retries: repeated invalid output multiplies token spend.
