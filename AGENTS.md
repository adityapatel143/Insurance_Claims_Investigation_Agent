# AGENTS.md — Project Memory: Insurance Claims Investigation Agent

Single source of truth for any agent/session working in this repo. Read fully before acting; update the
**Phase status** and **Handoff** sections at the end of every approval cycle.

## 1. Purpose and hard boundaries

Asynchronous **investigation assistant** for insurance claims on AWS (AgentCore Runtime + Gateway + Memory,
Bedrock + Guardrails, OpenSearch Serverless, S3, SQS, Lambda, DynamoDB, CloudWatch), deployed with
Terraform, Python managed with `uv`.

Never (in code, prompts, docs, or tests):
- approve, reject, price, pay, or decide eligibility for a claim;
- label a claimant fraudulent (use "potential anomaly signal" / "requires review");
- infer protected/sensitive attributes or diagnose medical conditions;
- use real people, real identifiers, or real claim data — synthetic only, labelled as such;
- add secrets to code, `.env.example`, Terraform state, logs, tests, or sample data.

All model output is advisory. Ambiguous, low-confidence, blocked, malformed, or anomalous outcomes → `REVIEW_REQUIRED`.

## 2. Working rules for agents

- **Never deploy to or create/modify resources in a real AWS account** (`terraform apply`, `docker push`,
  AWS CLI/SDK writes, seeding scripts) without explicit user approval for that specific action.
- One generation-order phase per approval cycle; stop and wait for approval after each phase.
- Generation and testing are separate: do not run test suites mid-generation unless asked.
- Be token-lean; never state unverified facts. Anything not verified against official docs/registry goes in §5.
- Use `uv` (`uv add`, `uv run`, `uv sync`); never raw `pip`/`venv`.
- Do not invent AWS APIs, SDK methods, or Terraform arguments — verify against the pinned provider docs first.
- Include only dependencies actually imported by generated code.
- Comments: one short line, only when the code cannot say it.

## 3. Confirmed decisions (user-approved 2026-09-30)

| Area | Decision | ADR |
|---|---|---|
| Processing model | API → DynamoDB job + SQS → orchestrator Lambda → AgentCore Runtime async task | 0001 |
| API front door | API Gateway HTTP API, IAM (SigV4) auth on all routes | 0001 |
| Agent runtime | AgentCore Runtime, container image in ECR, Strands Agents SDK + `bedrock-agentcore` SDK | 0002 |
| IaC for AgentCore | Native `aws_bedrockagentcore_*` resources (present in `hashicorp/aws` 6.66.0) | 0002 |
| Job status / idempotency | Single DynamoDB table, conditional writes, dispatch lease | 0003 |
| Human review | Advisory-only output; deterministic routing rules to `REVIEW_REQUIRED` | 0004 |
| Retrieval | OpenSearch Serverless `VECTORSEARCH` collection, IAM data-access; VPC endpoint optional | 0005 |
| Region default | `us-east-1` (examples only; never hardcoded in code) | — |
| Python | 3.13 (`.python-version`), `src/` layout, package `claims_investigator` | — |
| Lambda | Python 3.13, `arm64`, one shared zip artifact, one handler per function | — |
| Storage layout | One S3 bucket with prefixes `intake/ normalized/ reports/ quarantine/ sample-data/` | — |
| Encryption | Application bucket and Terraform state bucket use SSE-S3; no customer-managed KMS keys | — |
| Learning IAM | Every Lambda, Runtime, and Gateway role gets AWS-managed `AdministratorAccess` (user-approved 2026-10-01); never use with real data | — |
| Uploads | Presigned **POST** (policy enforces content-length-range + Content-Type) | 0001 |
| Terraform state | S3 backend with native lockfile (`use_lockfile = true`), two states per environment (foundation, platform) | — |
| Deployment stages | Stage 1 `foundation` (IAM roles/policies with name-derived exact ARNs), stage 2 `platform` (user-approved 2026-10-01) | — |
| Web app (2026-10-01) | Optional stack `web`: public S3 website (HTTP only), plain HTML/CSS/ES modules (no build), users paste temporary STS credentials (memory only); pure-JS SHA-256/SigV4 (WebCrypto unavailable on http://); CORS via platform `web_allowed_origins` | — |

## 4. Architecture summary

```
Client ──SigV4──> HTTP API ──> upload Lambda  (presigned POST → s3://…/intake/{claim_id}/…)
                           ├─> intake Lambda  (validate, HeadObject, quarantine mismatches,
                           │                   conditional put job QUEUED, SQS send, 202)
                           └─> status Lambda  (get job, derive timeout, presign report if owner)
SQS investigation queue ──(ReportBatchItemFailures)──> orchestrator Lambda
    (lease job, InvokeAgentRuntime with runtimeSessionId=f(job_id), mark PROCESSING)
    maxReceiveCount exceeded → mark FAILED, message → DLQ
AgentCore Runtime (Strands): evidence → retrieval → anomaly signals → risk → report
    reads intake/, writes normalized/ directly; all job/report writes via AgentCore Gateway tools
AgentCore Gateway → tools Lambda: get_claim_document_metadata, get_policy_guidance,
    search_similar_claims, persist_investigation_findings, update_job_status
AgentCore Memory: actorId = investigator principal hash, sessionId = job-scoped; summaries + preferences only
Bedrock Guardrail applied to model input/output via the Strands BedrockModel configuration
```

Job states: `QUEUED → PROCESSING → {COMPLETED | REVIEW_REQUIRED | FAILED}`; `QUEUED → FAILED` on exhausted dispatch.

## 5. Verification log

Verified (2026-09-30, via PyPI / Terraform registry / provider repo):
- `hashicorp/aws` latest 6.66.0; provider docs include `bedrockagentcore_agent_runtime`, `_agent_runtime_endpoint`,
  `_gateway`, `_gateway_target`, `_memory`, `_memory_strategy`, `_workload_identity`, `bedrock_guardrail`,
  `bedrock_guardrail_version`, `apigatewayv2_api`, `lambda_event_source_mapping`.
- PyPI latest: `strands-agents` 1.57.1, `bedrock-agentcore` 1.24.0, `boto3` 1.43.105, `pydantic` 2.13.5,
  `pydantic-settings` 2.15.0, `opensearch-py` 3.2.0 (all require Python ≥ 3.10).
- Local tooling: `uv` 0.9.15, Terraform 1.14.1, uv-managed CPython 3.13.10.
- (P4, botocore model / typed stubs) `invoke_agent_runtime(agentRuntimeArn, qualifier, runtimeSessionId[33..256],
  payload, contentType, accept)` → `statusCode`, `response` stream; `create_event(memoryId, actorId, sessionId,
  eventTimestamp, payload=[{conversational:{content:{text}, role}}])`; `list_memory_records(memoryId, namespace,
  maxResults)`; actorId pattern allows sha256 hex; sessionId max 100, `[a-zA-Z0-9][a-zA-Z0-9-_]*`.
- (P4, AWS docs) Titan Text Embeddings V2 body `{inputText, dimensions (256|512|1024), normalize}` → `{embedding}`.
- (P4, Powertools source) HTTP API v2 IAM identity at `requestContext.authorizer.iam.userArn`.
- (P4) opensearch-py 3.2.0 exports `Urllib3AWSV4SignerAuth(credentials, region, service)`, `Urllib3HttpConnection`.
- (P5, installed SDK source) `bedrock_agentcore.runtime.BedrockAgentCoreApp`: `@app.entrypoint` (sync handlers run
  in a threadpool; dict return → JSON 200), `add_async_task`/`complete_async_task` drive ping `HealthyBusy`;
  `app.run()` binds 0.0.0.0:8080 when `DOCKER_CONTAINER` is set.
- (P5) Strands 1.57.1: `BedrockModel(model_id, guardrail_id, guardrail_version, guardrail_trace, region_name,
  boto_client_config, temperature, max_tokens)`; `Agent(...)(prompt, structured_output_model=M, cancel_signal=Event)`
  → `AgentResult.stop_reason/structured_output`; stop reasons include `guardrail_intervened`, `content_filtered`;
  `StructuredOutputException`; `MCPClient(url=, auth_provider=httpx.Auth)`, `list_tools_sync`, `call_tool_sync`.
- (P5, botocore + AWS docs) Gateway `authorizerType` includes `AWS_IAM`; caller needs
  `bedrock-agentcore:InvokeGateway`; data-plane SigV4 signing name `bedrock-agentcore`; tool names are
  `${target}___${tool}`; Lambda target gets arguments as `event`, tool name in
  `context.client_context.custom["bedrockAgentCoreToolName"]`; tool schema keys limited to
  `type/properties/required/items/description`.
- (P6, `terraform providers schema -json` for aws 6.66.0) all resource arguments used in `infra/` exist;
  `lifecycle_configuration` on the runtime is a list-of-object *attribute*; gateway target `inline_payload` is a
  list block with `input_schema.property {name,type,description,required}`; memory strategy uses
  `namespace_templates` (exactly one); AgentCore name patterns: runtime/memory `[a-zA-Z][a-zA-Z0-9_]{0,47}`,
  gateway `([0-9a-zA-Z][-]?){1,48}`. Runtime also supports `code_configuration` (PYTHON_3_13); we use a container.
- (P6, AWS docs) AOSS Classic vector collections support HNSW with Faiss and k-NN `filter`; NextGen collections
  do not require `engine`. Titan V2 model ID `amazon.titan-embed-text-v2:0`, dimensions 256/512/1024.
- (P6) `terraform validate` passes for `bootstrap`, `environments/dev`, `environments/prod` (no backend, no AWS).

To verify at first deployment (needs user approval; cannot be verified offline):
- [ ] AgentCore Runtime accepts the arm64 image and `AWS_DEFAULT_REGION` override; runtime role permissions suffice.
- [ ] Gateway returns the Lambda JSON as MCP text/structured content as `gateway_client._envelope` expects;
  SigV4 over MCP streamable HTTP accepted by Gateway.
- [ ] Index mapping (explicit `faiss`/`hnsw`/`l2`) accepted by the collection generation the provider creates.
- [ ] `InvokeAgentRuntime` IAM resource form (`runtime ARN` and `ARN/*` granted).
- [ ] Presigned upload works with bucket default SSE-S3 encryption after the dev platform is deliberately
  migrated; live upload retest pending.

## 6. Planned repository tree

Repo root = this workspace (`insurance-claims-investigation-agent`). `(+)` = addition beyond the requested tree.

```text
.
├── AGENTS.md (+)            README.md   ARCHITECTURE.md   CONTRIBUTING.md   SECURITY.md
├── CHANGELOG.md             LICENSE     pyproject.toml    uv.lock
├── .python-version          .env.example  .gitignore      .editorconfig     .secrets.baseline (+)
├── docs/
│   ├── architecture-diagram.md  data-flow.md  threat-model.md  operations-runbook.md
│   ├── testing-strategy.md  cost-considerations.md  privacy-and-retention.md
│   └── adr/ 0001-asynchronous-processing.md  0002-agentcore-runtime.md
│            0003-job-status-dynamodb.md  0004-human-review-boundary.md  0005-opensearch-serverless.md (+)
├── src/claims_investigator/
│   ├── __init__.py  config.py  logging.py  errors.py (+)  metrics.py (+)  runtime.py (+ AgentCore entrypoint)
│   ├── storage_keys.py (+ S3 key layout)
│   ├── models/    common.py (+)  api.py  jobs.py  messages.py  evidence.py  findings.py  result.py
│   ├── agents/    evidence.py  context.py (+)  fraud_signals.py  risk.py  report.py  pipeline.py
│   ├── services/  ports.py (+ Protocols)  jobs.py  uploads.py  intake.py  status.py  dispatch.py (+)
│   │              retrieval.py  human_review.py  memory.py  guardrails.py
│   ├── gateways/  AWS SDK adapters behind Protocols: aws.py (+ client config/errors)  s3.py  dynamodb.py  sqs.py
│   │              opensearch.py  embeddings.py  agentcore_runtime.py  agentcore_memory.py  gateway_client.py
│   │              bedrock_model.py (+ Strands StructuredModel)
│   ├── handlers/  http.py (+)  upload.py  intake.py  status.py  orchestrator.py  gateway_tools.py
│   ├── tools/     schemas.py  tool_definitions.json (+ Gateway + Terraform source)  dispatcher.py
│   └── prompts/   __init__.py (loader)  policy.md  anomaly_signals.md  risk_assessment.md  report.md
├── tests/  conftest.py (+)  fakes.py (+ Protocol fakes, World, DispatcherBackedTools)
│       unit/  contract/  integration/ (opt-in, deployed stack)  fixtures/ (synthetic documents, message, result)
├── scripts/  _common.py (+)  seed_sample_data.py  create_index.py  submit_sample_claim.py  check_job.py
│             destroy_environment.py (+)
│   └── sh/ (+)  _lib.sh (sourced)  one bash script per task (replaces the Makefile), .shellcheckrc
├── sample-data/  README.md  claims/{complete,missing-documents,inconsistent}/ (claim.json + docs)
│                guidance/*.md  historical/*.md (front matter: title, claim_type, source_type)
├── docker/runtime.Dockerfile   .dockerignore (+)
├── infra/
│   ├── bootstrap/                      SSE-S3 state bucket (S3 native locking), local state
│   ├── modules/ s3 sqs dynamodb lambda iam api-gateway (+) ecr (+) opensearch
│   │            bedrock-guardrail agentcore-memory agentcore-gateway agentcore-runtime observability
│   │            naming (+ single source of resource names/ARNs) foundation (+ stage 1: naming+iam)
│   │            platform (+ stage 2: everything else)
│   └── environments/{dev,prod}/ backend.hcl.example common.tfvars.example (+ shared by both stacks)
│                foundation/ (+) versions.tf providers.tf backend.tf variables.tf locals.tf main.tf outputs.tf
│                platform/ versions.tf providers.tf backend.tf variables.tf locals.tf
│                main.tf outputs.tf terraform.tfvars.example (each stack has .terraform.lock.hcl)
└── .github/workflows/ quality.yml  security.yml  terraform.yml      (+ .checkov.yaml at repo root)
```

Note: `gateways/` = AWS SDK adapter layer (gateway pattern). AgentCore Gateway tool definitions live in `tools/`.

## 7. Phase plan and status

| # | Phase | Status |
|---|---|---|
| 1 | Architecture decisions (ADRs), repository tree, repo hygiene files | done (approved) |
| 2 | `uv` project, `pyproject.toml`, `config.py`, `logging.py`, `errors.py`, Pydantic models | done (approved) |
| 3 | Domain services and Protocol interfaces | done (approved) |
| 4 | AWS adapters (`gateways/`) and Lambda handlers | done (approved) |
| 5 | AgentCore Runtime agent (Strands), Gateway tools, prompts, Dockerfile | done (approved) |
| 6 | Terraform bootstrap, modules, environments | done (approved) |
| 7 | Tests and fixtures | done (approved; some failures parked by user until the final test phase) |
| 8 | Sample data and scripts | done (approved) |
| 9 | README, ARCHITECTURE, docs/*, remaining root docs | done (approved) |
| 10 | CI workflows, `.secrets.baseline` | done (approved) |
| 11 | Consistency review, then test/verify phase (on user go-ahead) | local verification done; this Terraform validation blocked by provider download; AWS deployment not performed |

## 8. Code conventions (established in Phase 2)

- Env vars: prefix `CLAIMS_` (e.g. `CLAIMS_BUCKET_NAME`); region from `AWS_REGION`. No `.env` auto-loading.
  Per-component settings classes in `config.py` (`UploadSettings`, `IntakeSettings`, `StatusSettings`,
  `OrchestratorSettings`, `ToolsSettings`, `RuntimeSettings`); `.env.example` lists every variable.
- S3 keys only via `storage_keys.py`: `intake/{claim}/{doc}/{file}`, `normalized/{claim}/{job}/submission.json`,
  `normalized/{claim}/{job}/documents/{doc}.json`, `reports/{claim}/{job}/report.{json,md}`, `quarantine/…`.
- Claim narrative is stored only in the S3 submission object; DynamoDB/SQS hold identifiers and pointers.
- Evidence IDs: `doc:{document_id}#L{n}`, `meta:{field}`, retrieved sources `src:{chunk_id}`.
- `models/common.py::ensure_advisory_language` rejects fraud labels, adjudication, eligibility, and diagnosis
  wording in generated text; `InvestigationResult` validates grounding (all cited IDs must exist).
- Logging: `log_event(logger, level, event, **fields)` + `log_context(...)`; sensitive keys are redacted.
- Runtime deps so far: `pydantic`, `pydantic-settings`. Dev: ruff, mypy, pytest, pytest-cov, bandit, detect-secrets.
- Static checks: `uv run ruff format src && uv run ruff check src && uv run mypy` (strict).
- Services depend only on Protocols in `services/ports.py` (`ObjectStore`, `JobRepository`, `QueuePublisher`,
  `AgentRuntimeInvoker`, `Embedder`, `VectorSearch`, `MemoryStore`) plus an injectable `Clock`.
- Status writes go through `JobService.transition` (transition map + conditional repo write).
  QUEUED→PROCESSING may be done by either the orchestrator or the runtime's `update_job_status` tool.
- Dispatch: lease → invoke → PROCESSING; invoke failure releases lease and re-raises; on last receive marks
  FAILED `DISPATCH_EXHAUSTED` first. Duplicates/unknown jobs return `SKIPPED` (acked).
- Memory: `actor_id = sha256(principal)`, session `claims-job-{job_id}`; summaries are codes/counts only;
  memory failures degrade to empty context.
- Human review: `services/human_review.assess_review` is the only routing authority.
- Adapters translate throttling/5xx/botocore errors to `DependencyUnavailableError`; boto3 clients use
  `gateways/aws.client_config()` (standard retry mode, bounded attempts, explicit timeouts).
- DynamoDB timestamps are fixed-width UTC strings `%Y-%m-%dT%H:%M:%S.%fZ` (lexicographic = chronological);
  `expires_at` is epoch seconds (TTL attribute).
- Memory namespaces (must match Terraform strategies): `/claims/preferences/{actorId}`,
  `/claims/summaries/{actorId}/{sessionId}`.
- OpenSearch index: strict mapping, vector field `embedding`; guidance with `claim_type=GENERAL` matches all types.
- Handlers: settings + clients built once per cold start via `@cache def _service()`; API responses carry
  `x-correlation-id`, `cache-control: no-store`; 5xx bodies are generic. EMF metrics via `metrics.emit`
  (namespace `ClaimsInvestigator`, dimension `Environment`).
- Orchestrator: invalid messages and dispatch errors are reported in `batchItemFailures` (→ DLQ after max receives).
- Dependencies: agent-only deps live in the `agent` dependency group (`strands-agents`, `bedrock-agentcore`,
  `httpx`); `[tool.uv] default-groups = ["dev", "agent"]` so plain `uv sync`/`uv run` include them.
  Lambda bundle: export with `--no-default-groups` (no agent deps); image: `--no-default-groups --group agent`.
- Runtime: entrypoint validates `RuntimeInvocation`, dedupes by job in-process, starts a thread tracked with
  `add_async_task`, returns `{"status":"ACCEPTED"}`. A `threading.Timer` sets the Strands `cancel_signal` at
  `min(processing_deadline, now + investigation_timeout)`; timeout → FAILED `TIMEOUT`.
- The LLM has **no tools**. Tool calls are made by pipeline code only (prompt injection cannot widen tool scope).
- Tools: `update_job_status` may only set PROCESSING/FAILED; `persist_investigation_findings` validates the full
  `InvestigationResult`, re-checks `minimum_review_reasons`, writes `reports/`, and derives the terminal status.
  All tools require matching `claim_id` + `correlation_id`; reads/persist require job `PROCESSING`.
  Lambda responses use `ToolEnvelope {ok, result | error}`.
- Model failures (guardrail/invalid output) degrade to deterministic fallbacks, cap confidence at 0.3, and force
  review. Rule-based signals: AMOUNT/INCIDENT_DATE/POLICY_REFERENCE mismatch, REPORTED_BEFORE_INCIDENT,
  LATE_REPORTING (>30 days). Required documents per claim type live in `agents/evidence.REQUIRED_DOCUMENTS`.
- Supported extraction: `text/plain` (`Key: Value` lines), `text/csv` (`field,value` rows or header+row),
  `application/json` (object, one nesting level).

### Terraform conventions (Phase 6)

- Terraform `>= 1.11, < 2`; provider `~> 6.66`; lock files committed; every module has `versions.tf`.
- Names: `name_prefix = "${app_name}-${environment}"` (app_name ≤ 23 chars for AOSS 32-char limits);
  Lambdas `<prefix>-{upload,intake,status,orchestrator,tools}`; AgentCore names replace `-` with `_`.
- Two-step deploy: apply with `agent_image_tag = null` (runtime not created, SQS mapping disabled),
  push image, apply with the tag. The orchestrator is a separate module instance to avoid a dependency cycle;
  its `InvokeAgentRuntime` policy lives in `modules/platform`.
- Two stacks per env: `foundation` (state key `claims-investigator/<env>/foundation.tfstate`) is applied
  before `platform` (key `.../<env>/terraform.tfstate`). Foundation policies use only ARNs derivable from
  `modules/naming`; permissions on service-generated-ID resources (guardrail, memory, gateway, AOSS
  collection, runtime) are `resource-access` role policies in `modules/platform/iam.tf` (exact ARNs, user
  rejected name-prefix wildcards). Platform finds roles via `data.aws_iam_role` (plan fails if foundation
  missing). Application services use AWS-managed/service-managed encryption; Terraform state continues to
  use SSE-S3.
  Shared vars in `<env>/common.tfvars` (`-var-file=../common.tfvars`), platform-only in
  `platform/terraform.tfvars`, backend config `<env>/backend.hcl`. Scripts: `tf_{init,plan,apply}.sh <env>
  <foundation|platform>`; `destroy.sh` destroys platform then foundation.
- Lambda zip path `dist/lambda.zip` (built by `scripts/sh/build_lambda.sh`); `filebase64sha256` needs it at plan time.
- Gateway tool schema comes from `src/claims_investigator/tools/tool_definitions.json` via `jsondecode(file())`.
- Env differences live in `environments/<env>/{foundation,platform}/locals.tf` `settings`; required user input: `region`, `model_id`
  (validation rejects the `REPLACE...` placeholder), optional `indexer_principal_arns`, `alarm_email`.
- Runtime container gets `AWS_DEFAULT_REGION` (not `AWS_REGION`) from Terraform.
- Credentials: AWS CLI named profile only (`AWS_PROFILE` or `PROFILE=<name> scripts/sh/...`;
  `scripts/sh/whoami.sh`). Never
  add access keys to tfvars, backend.hcl, .env, or the repo (user-agreed; README "AWS credentials").
- Task runner: no Makefile. One bash script per task in `scripts/sh/` (`--help` prints the header; `[AWS]` in the
  header marks scripts that touch an account; `<env>` = dev|prod validated before any AWS call). Common code in
  `_lib.sh` (`set -euo pipefail`, cds to repo root, `PROFILE`→`AWS_PROFILE`). CI calls `build_lambda.sh` and
  `tf_validate.sh`. ShellCheck clean (`uvx --from shellcheck-py shellcheck -s bash scripts/sh/*.sh`).
- Portability (Linux + macOS): scripts limited to bash 3.2 / BSD userland features (`${1+"$@"}` for empty
  args); script
  HTTPS goes through `_common.https_open` (certifi CA bundle, HTTPS-only); `certifi` is a direct dependency.
  Terraform lock files carry `zh:` hashes for all platforms. Reviewed, not executed on a Mac.
- Alarms: SQS oldest-message age, DLQ depth, per-Lambda Errors/Throttles, `JobsFailed` (EMF); SNS messages contain only non-claim metrics/resource names and use no customer-managed key.

### Test conventions (Phase 7)

- `uv sync` then `uv run pytest` (default excludes `-m integration`; `pythonpath = ["."]`).
- `tests/conftest.py` autouse fixture sets fake AWS credentials, `AWS_CONFIG_FILE=/dev/null`, disables IMDS, and
  unsets `AWS_PROFILE` for every non-integration test, so unit tests cannot reach a real account.
- Fakes replace only AWS/model boundaries (`tests/fakes.py`); domain logic, agents, and the tools dispatcher run
  for real. Adapters use botocore `Stubber` or a recording Table fake. Runtime-side tests `importorskip` the
  `agent` extra.
- Contract tests check tool JSON vs Pydantic models and Gateway keyword subset, settings vs Terraform env vars and
  `.env.example`, memory namespaces vs Terraform, handler paths, and `terraform fmt -check` (if installed).
- Integration test needs `CLAIMS_IT_API_ENDPOINT` + real credentials; only run with explicit user approval.

## 9. Handoff

Phase 1: `AGENTS.md`, `docs/adr/0001`–`0005`, `.python-version`, `.gitignore`, `.editorconfig`.
Phase 2: `pyproject.toml`, `uv.lock`, `.env.example`, `src/claims_investigator/{__init__,config,logging,errors,
storage_keys}.py`, `models/{common,api,jobs,messages,evidence,findings,result}.py`. Ruff + mypy strict pass;
no tests written or run yet. `LICENSE`/`readme` metadata deferred to Phase 9.
Phase 3: `services/{ports,jobs,uploads,intake,status,dispatch,retrieval,human_review,memory,guardrails}.py`;
`JobRecord.enqueue_count`, `ReviewReason.UNTRUSTED_INSTRUCTIONS_DETECTED`, error `details`. Ruff + mypy pass.
Next: Phase 4 (AWS adapters + Lambda handlers; adds `boto3`).
Phase 4: `metrics.py`, `gateways/{aws,s3,dynamodb,sqs,opensearch,embeddings,agentcore_runtime,agentcore_memory}.py`,
`handlers/{http,upload,intake,status,orchestrator}.py`, `models.api.JobStatusPath`. Deps: `boto3`, `opensearch-py`;
dev `boto3-stubs[s3,dynamodb,sqs,bedrock-agentcore,bedrock-runtime]`. Ruff + mypy pass. Nothing run against AWS.
`gateway_client.py` and `handlers/gateway_tools.py` moved to Phase 5 (they depend on tool schemas).
Phase 5: `runtime.py`, `agents/{evidence,context,fraud_signals,risk,report,pipeline}.py`,
`gateways/{gateway_client,bedrock_model}.py`, `handlers/gateway_tools.py`, `tools/{schemas,dispatcher}.py`,
`tools/tool_definitions.json`, `prompts/*`, `docker/runtime.Dockerfile`, `.dockerignore`. Also: `RetrievedChunk` moved
to `models/findings.py`, `ToolCallError`, `minimum_review_reasons`, new settings (`CLAIMS_MAX_DOCUMENT_BYTES`,
`CLAIMS_TOOL_TIMEOUT_SECONDS`, tools `CLAIMS_REVIEW_CONFIDENCE_THRESHOLD`), deps `botocore` + `agent` extra.
Ruff + mypy pass; wheel verified to include prompts/JSON. No image built, nothing run against AWS.
Phase 6: `infra/bootstrap`, 15 modules under `infra/modules` (incl. `platform`), `infra/environments/{dev,prod}`,
lock files, `.gitignore` for `backend.hcl`. Python: `JobsFailed` metric on dispatch exhaustion and deadline timeout.
`terraform fmt` + `validate` pass; no plan/apply; scratch provider schema in /tmp only.
Phase 7: `tests/{conftest,fakes}.py`, `tests/unit/*` (models, config, messages, API services, dispatch, human
review, guardrails, retrieval/memory, agents, pipeline, tool dispatcher, handlers, AWS adapters, runtime side),
`tests/contract/test_contracts.py`, `tests/integration/test_end_to_end.py`, `tests/fixtures/*`. pytest config:
`pythonpath`, default `-m 'not integration'`; test-only ruff ignores. Ruff passes; **tests not executed yet**
(per generation/testing split) — expect fixes in the test phase; coverage gate is 80%.
Next: Phase 8 (sample data and scripts).
Phase 8: `sample-data/` (3 claim scenarios with `claim.json` manifests, 4 guidance + 3 historical markdown files,
README), `scripts/{_common,create_index,seed_sample_data,submit_sample_claim,check_job}.py`,
`OpenSearchVectorSearch.delete_index`. Agent deps moved from extra to `agent` group (+ `default-groups`);
Dockerfile updated. Manifests verified offline against `ClaimSubmission`; scripts only `--help`-checked;
nothing run against AWS. User-run pytest had failures: parked for Phase 11.
Next: Phase 9 (README, ARCHITECTURE, docs/*, root docs, Makefile incl. `build-lambda` -> `dist/lambda.zip`).
Phase 9: `README.md`, `ARCHITECTURE.md`, `docs/{architecture-diagram,data-flow,threat-model,operations-runbook,
testing-strategy,cost-considerations,privacy-and-retention}.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md`,
`LICENSE` (MIT, assumed), `Makefile`; pyproject `readme`/`license`, `[tool.bandit]`, removed empty `agent` extra.
`make build-lambda` verified locally (27 MB zip, arm64 wheels, no agent deps). Docs cite no prices.
Next: Phase 10 (CI workflows + `.secrets.baseline`).
Phase 10: `.github/workflows/{quality,security,terraform}.yml` (actions pinned by commit SHA, verified via
`git ls-remote`: checkout v7.0.1, setup-uv v10.2.0, setup-terraform v4.0.1, checkov-action v12.3127.0,
upload-artifact v7.0.1; read-only permissions; no AWS credentials, no deploy). `.checkov.yaml` with justified
skips; bootstrap KMS key policy + multipart abort added. `.secrets.baseline` (clean; two test placeholders
allowlisted inline). Locally verified: Checkov 0 failed, Bandit clean (3 audited `nosec B310`), detect-secrets
clean, `make tf-validate` passes. Workflows not executed on GitHub (no repo/remote).
Next: Phase 11 (consistency review, then fix parked test failures on user go-ahead).
Phase 11 (local): 234 passed, 1 deselected (integration), coverage 90% (gate 80%). One real bug fixed:
`models/api.ContentType` now lower-cases via `BeforeValidator` (StringConstraints checks `pattern` before
`to_lower`). ruff, mypy strict, Bandit, detect-secrets, terraform fmt/validate all pass. Only remaining warning
is a `datetime.utcnow` DeprecationWarning inside the `bedrock-agentcore` SDK. Not verified: Mermaid rendering,
GitHub Actions execution, and everything in §5 "To verify at first deployment" (needs user approval).
Cleanup: `scripts/destroy_environment.py` + `make destroy ENV=dev CONFIRM=dev` (confirm guard, prod refused
without `--allow-prod`, interactive confirm after `plan -destroy`, deletes runtime log groups containing the
runtime ID under `/aws/bedrock-agentcore/runtimes/`; exact log-group naming unverified until deployment).
Only refusal guards and `--help` were exercised; never run against AWS.
Makefile → `scripts/sh/*.sh` (user-requested; Makefile deleted; earlier `make X` mentions above are history).
Updated README (new "Task scripts" table), CONTRIBUTING, docs, CI, tfvars examples, variable descriptions,
`destroy_environment.py` messages, `.editorconfig`. Verified locally: `bash -n` + ShellCheck clean, every
`--help`, env/arg guards, `check.sh` (234 passed, 90% coverage, ruff/mypy/bandit/detect-secrets/tf fmt),
`tf_validate.sh`, `build_lambda.sh` (no agent deps), `clean.sh`. AWS-touching scripts only guard-tested;
not run on a Mac.
Staged deploy (2026-10-01, user-requested): env roots split into `foundation/` + `platform/`, new modules
`naming` and `foundation`, stage-2 policies in `modules/platform/iam.tf`, s3/dynamodb/sqs/ecr take explicit
names, scripts take `<env> <stack>`. Verified offline: fmt, validate (all 4 stacks), ShellCheck, ruff, pytest
(234 passed), arg guards. Not applied. Existing partial dev deployment was created by the old single stack:
it must be destroyed with the previous commit before using the new layout (IAM role names would collide).
Web app (2026-10-01, user-requested): `web/` (index.html, css/, js/{sha256,sigv4,api,model,store,dom,report,
app}.js, tests/ for `node --test`), `scripts/build_web.py` (+ samples/index.json, config.json),
`scripts/sh/web_{build,serve,deploy}.sh`, module `web-hosting` + stacks `environments/<env>/web` (state
`.../<env>/web.tfstate`), naming `web_bucket_name`, `cors_configuration` on the HTTP API and S3 CORS on the data
bucket (both from `web_allowed_origins`), README section 6, threat model T16, scoped `#checkov:skip`s.
Verified offline: JS tests vs node:crypto, SigV4 parity with botocore (`tests/unit/test_web.py`), pytest 238
passed, ruff, mypy, ShellCheck, fmt/validate (6 stacks), Checkov 0 failed, security.sh. Not verified: browser
rendering/UX, real CORS/preflight behaviour, account-level Block Public Access, S3 website endpoint.
CORS opened (user-requested): dev `web_allowed_origins` defaults to `["*"]` (prod `[]`); `tf_plan.sh <env> web`
does a read-only account Block Public Access check and stops early. Both still unverifiable offline.
Sharing: `scripts/sh/share_clean.sh` (dry run default; `--yes` deletes local config + generated files;
`--archive x.tar.gz` packs git-tracked + untracked non-ignored files). Never deletes `*.tfstate`.
Learning simplification (user-approved 2026-10-01): no customer-managed KMS keys; S3 application/state buckets
and ECR use AES256, SQS managed SSE, DynamoDB/AOSS/service defaults; SNS alarm contents are non-claim
metrics/resource names and are not encrypted. Backend config omits `kms_key_id` and `tf_init.sh` uses
`-reconfigure`. Bootstrap no longer manages the legacy state key; before applying, re-encrypt or expire all
historical state object versions that use it. No IAM Deny policies. Every Lambda,
Runtime, and Gateway role attaches `AdministratorAccess` (account-wide, explicitly learning-only); deployer
credentials are still not passed into workloads. Checkov has scoped skips for this model. Verified offline:
fmt, all 7 Terraform roots validate, Checkov 0 failed. Pytest before latest IAM-only edits: 238 passed/1
deselected. `check.sh` stopped at detect-secrets on fixture detections in `web/tests/model.test.js` and
`web/tests/sha256.test.js`. Not applied. Existing app/state objects may remain KMS-encrypted: migrate or
discard old S3/state versions before scheduling old keys for deletion. Never use this configuration with
real claim data or a shared AWS account.
KMS removal (2026-10-05): bootstrap no longer declares a customer-managed state key; backend encryption is
SSE-S3. Terraform formatting, Ruff on touched Python files, and `git diff --check` pass. `terraform validate`
could not run because the pinned AWS provider was missing locally and its registry download reset; no AWS
apply was run. Re-encrypt or expire old state versions before applying the key removal.
