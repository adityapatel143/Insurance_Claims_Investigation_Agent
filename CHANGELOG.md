# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses semantic versioning.

## [Unreleased]

### Added

- Asynchronous intake and status API (API Gateway HTTP API, IAM auth) with presigned S3 POST uploads,
  quarantine of mismatched uploads, and idempotent job creation in DynamoDB.
- SQS-driven orchestrator with dispatch leases, partial batch failures, and a dead-letter queue.
- AgentCore Runtime agent (Strands) with evidence extraction, rule-based and model-assisted potential
  anomaly signals, risk assessment, deterministic human-review routing, and JSON + Markdown reports.
- AgentCore Gateway with five approved tools backed by a validating tools Lambda.
- AgentCore Memory integration limited to job-scoped summaries of codes and counts.
- Bedrock Guardrail with denied topics, content and prompt-attack filters, and PII anonymization.
- OpenSearch Serverless retrieval over synthetic guidance and historical examples.
- Terraform bootstrap, 15 modules, and `dev`/`prod` environments.
- Unit, contract, and opt-in integration tests; synthetic sample data and operator scripts.
- Architecture, data-flow, threat-model, runbook, testing, cost, and privacy documentation; ADRs 0001-0005.
