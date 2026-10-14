"""Explicit exception types; each carries an HTTP-safe code and a retryability flag."""

from claims_investigator.models.jobs import FailureCategory


class ClaimsInvestigatorError(Exception):
    code = "INTERNAL_ERROR"
    http_status = 500
    retryable = False
    failure_category = FailureCategory.INTERNAL

    def __init__(self, message: str = "", details: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class RequestValidationError(ClaimsInvestigatorError):
    code = "VALIDATION_ERROR"
    http_status = 400


class DocumentRejectedError(ClaimsInvestigatorError):
    """An uploaded object failed size/type/key checks and was quarantined."""

    code = "DOCUMENT_REJECTED"
    http_status = 422


class NotFoundError(ClaimsInvestigatorError):
    code = "NOT_FOUND"
    http_status = 404


class ForbiddenError(ClaimsInvestigatorError):
    code = "FORBIDDEN"
    http_status = 403


class IdempotencyConflictError(ClaimsInvestigatorError):
    """Same idempotency key reused with a different request body."""

    code = "IDEMPOTENCY_CONFLICT"
    http_status = 409


class JobTransitionError(ClaimsInvestigatorError):
    """A conditional status write lost a race or violated the transition map."""

    code = "JOB_TRANSITION_CONFLICT"
    http_status = 409


class DependencyUnavailableError(ClaimsInvestigatorError):
    code = "DEPENDENCY_UNAVAILABLE"
    http_status = 503
    retryable = True
    failure_category = FailureCategory.DEPENDENCY_UNAVAILABLE


class ToolArgumentError(ClaimsInvestigatorError):
    code = "INVALID_TOOL_ARGUMENTS"
    http_status = 400
    failure_category = FailureCategory.TOOL_ERROR


class ToolCallError(ClaimsInvestigatorError):
    """A Gateway tool call failed or returned an error envelope."""

    code = "TOOL_CALL_FAILED"
    failure_category = FailureCategory.TOOL_ERROR


class GuardrailInterventionError(ClaimsInvestigatorError):
    """Bedrock Guardrails blocked model input or output; routes to human review."""

    code = "GUARDRAIL_INTERVENED"


class ModelOutputError(ClaimsInvestigatorError):
    """Model output was malformed or failed validation after bounded retries."""

    code = "MODEL_OUTPUT_INVALID"


class InvestigationTimeoutError(ClaimsInvestigatorError):
    code = "INVESTIGATION_TIMEOUT"
    http_status = 504
    failure_category = FailureCategory.TIMEOUT
