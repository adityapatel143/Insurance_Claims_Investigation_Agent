# Testing strategy

## Layers

| Layer | Location | What it covers | AWS access |
|---|---|---|---|
| Unit | `tests/unit/` | Models and validation, settings, services, dispatch and idempotency, human-review routing, guardrails, retrieval, memory, evidence extraction, rule signals, report assembly, the full pipeline, the tools dispatcher, Lambda handlers, AWS adapters, runtime-side adapters | None |
| Contract | `tests/contract/` | Gateway tool JSON vs Pydantic models and the Gateway schema subset; required result and message fields; Terraform env vars vs settings classes and `.env.example`; memory namespaces vs Terraform; handler paths; `terraform fmt` | None |
| Integration | `tests/integration/` | Upload, submit, and poll a synthetic claim through the deployed API | Real (opt-in) |
| Infrastructure | `scripts/sh/tf_validate.sh` | Terraform syntax and provider schema for bootstrap, dev, prod | None (no backend) |

## Principles

- Mock AWS boundaries, not domain logic: `tests/fakes.py` provides in-memory implementations of the
  Protocols in `services/ports.py`; agents, services, and the tools dispatcher run for real.
- The pipeline tests route tool calls through the real `ToolDispatcher` (`DispatcherBackedTools`), so
  scoping, validation, and status derivation are exercised end to end in-process.
- AWS adapters use botocore `Stubber` (validated against service models) or a recording table fake.
- `tests/conftest.py` sets fake credentials, disables instance metadata, and blanks AWS config files for
  every non-integration test.
- Fixtures are synthetic and labelled as such.

## Scenarios covered

Request and result validation; SQS message parsing; idempotent job creation and conflicts; partial batch
failures; status transitions and timeouts; guardrail-blocked responses; malformed model output;
retrieval with and without results; evidence-reference preservation and ungrounded-finding removal;
human-review routing for every reason; Lambda handler status codes and error mapping; Gateway tool
schemas and envelopes.

## Commands

```bash
scripts/sh/test.sh       # unit + contract with coverage (gate: 80% in pyproject.toml)
uv run pytest tests/unit/test_pipeline.py -q
CLAIMS_IT_API_ENDPOINT=https://<api>.execute-api.<region>.amazonaws.com scripts/sh/test_integration.sh
```

Run the integration test only against a stack you own; it creates jobs and S3 objects and invokes Bedrock.
