# Contributing

## Ground rules

- Read [AGENTS.md](AGENTS.md) first: it holds the hard boundaries, conventions, and verification log.
- The system is advisory only. Changes must not add any path that approves, rejects, prices, or pays a
  claim, labels a person fraudulent, infers protected attributes, or diagnoses conditions.
- Use synthetic data only. Never commit real personal data, secrets, account-specific `terraform.tfvars`,
  or `backend.hcl`.
- Verify AWS APIs, SDK methods, and Terraform arguments against official documentation or the pinned
  provider schema; record new findings in `AGENTS.md` §5.

## Development setup

```bash
uv sync           # dev + agent dependency groups
scripts/sh/check.sh   # lint, mypy, tests, security scans, terraform fmt
```

## Making changes

1. Keep domain logic in `services/` and `agents/` behind the Protocols in `services/ports.py`; AWS SDK
   calls belong in `gateways/`.
2. Add or update tests with the change: unit tests for logic, contract tests when a schema, tool, or
   Terraform wiring changes. Mock only AWS and model boundaries.
3. When adding a setting, add it to `config.py`, `.env.example`, and the Terraform environment map; the
   contract tests check all three.
4. When changing a Gateway tool, update `tools/tool_definitions.json` and the Pydantic models together.
5. Keep comments to a single line and only where the code cannot speak for itself.
6. Update `CHANGELOG.md` under "Unreleased".

## Pull requests

- CI must pass (quality, security, terraform workflows).
- Describe any change to human-review routing, prompts, guardrail policies, or IAM explicitly; these
  require review by a second maintainer.
- No automatic deployment: maintainers deploy with `scripts/sh/tf_plan.sh` / `scripts/sh/tf_apply.sh`
  after review.
