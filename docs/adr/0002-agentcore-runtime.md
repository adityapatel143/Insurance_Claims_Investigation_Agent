# ADR 0002: AgentCore Runtime with Strands, native Terraform resources

- Status: Accepted
- Date: 2026-09-30

## Context

The investigation workflow needs managed, isolated, long-running agent execution with session isolation,
controlled tool access, and managed memory. It must be deployable with Terraform.

## Decision

1. **Execution:** Amazon Bedrock AgentCore Runtime hosts the agent as a container image stored in ECR.
   The entrypoint uses the `bedrock-agentcore` Python SDK (`BedrockAgentCoreApp`). The invocation
   acknowledges immediately and runs the investigation as a background async task so the orchestrator
   Lambda is not held open.
2. **Agent framework:** Strands Agents SDK for model calls and structured output. Domain logic
   (evidence normalization, anomaly rules, human-review routing, report assembly) is plain Python in
   `agents/` and `services/`, independent of Strands, so it can be unit-tested without a model.
3. **Session isolation:** `runtimeSessionId` is derived deterministically from `job_id`, so one job maps to
   one session and cannot share context with another claim.
4. **Tools:** AgentCore Gateway exposes five approved tools backed by one tools Lambda
   (`get_claim_document_metadata`, `get_policy_guidance`, `search_similar_claims`,
   `persist_investigation_findings`, `update_job_status`). Each tool has a strict JSON schema; arguments
   are re-validated with Pydantic inside the Lambda. Job and report writes happen only through tools.
5. **Direct access kept minimal:** the runtime role may read `intake/*` and write `normalized/*` in S3,
   invoke the configured model/guardrail, and use its Memory resource. It has no DynamoDB, SQS, or
   OpenSearch permissions.
6. **Infrastructure as code:** `hashicorp/aws` 6.66.0 includes native resources
   (`aws_bedrockagentcore_agent_runtime`, `_agent_runtime_endpoint`, `_gateway`, `_gateway_target`,
   `_memory`, `_memory_strategy`). These are used directly; no custom deployment adapter is needed.
   The provider is pinned with `~> 6.66`.

## Consequences

- The container image must exist in ECR before the runtime resource is created; the deployment sequence
  (ECR → build/push → full apply) is documented in the README.
- Provider upgrades must be reviewed because AgentCore resources are relatively new.
- Exact SDK/provider argument names are verified before implementation (tracked in `AGENTS.md` §5).

## Alternatives considered

- **Agent logic inside Lambda:** rejected — 15-minute limit and no managed session/memory isolation.
- **Bedrock Agents (classic):** rejected — requirement specifies AgentCore.
- **AgentCore starter toolkit CLI for deployment:** rejected — would split infrastructure ownership outside Terraform.
