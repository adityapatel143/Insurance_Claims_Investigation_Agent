# Security policy

## Reporting a vulnerability

Do not open a public issue for security problems. Report privately to the repository maintainers through
your organisation's security contact or the hosting platform's private vulnerability reporting, with
steps to reproduce and the affected commit. Do not include real personal data in reports.

## Supported versions

Only the latest commit on the default branch is supported.

## Security design summary

- IAM (SigV4) authorization on every API route and on the AgentCore Gateway; no anonymous access.
- Least-privilege IAM roles per component; S3 access scoped by prefix.
- AWS-managed/service-managed encryption for data at rest; TLS enforced by resource policies.
- No secrets in code, configuration examples, Terraform state, logs, tests, or sample data. The design
  needs no application secrets; AWS credentials come from IAM roles.
- Input validation with Pydantic at every boundary; presigned uploads constrained by type and size;
  quarantine for mismatched uploads.
- Prompt-injection defences: untrusted-data fencing, injection markers routed to human review, a model
  without tools, schema and grounding validation of output, and Bedrock Guardrails.
- Structured logs without claim content; audit trail through job transitions, tool-call logs, API access
  logs, and CloudTrail.
- Human approval for every consequential action: the system produces advisory reports only.

See [docs/threat-model.md](docs/threat-model.md) for threats, mitigations, and residual risks.

## Automated checks

CI runs Bandit, detect-secrets (against `.secrets.baseline`), ruff, mypy, pytest, and Terraform
`fmt`/`validate` plus a static IaC security scan. Production deployment is never automatic.
