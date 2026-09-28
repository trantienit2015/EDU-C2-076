"""AgentCore Platform v1.0 — inner step 1: sensitive-content minimization."""

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services import eligibility_service as es


class SensitiveContentMinimizationNode(FunctionNode):
    """Detect applicant names, personnel identifiers, unpublished research
    detail; request the minimum + mask per approved policy
    (Step 2).

    The inner subgraph receives only the JSON string user_input (seeded from
    the outer validated_input), so this first inner node reconstructs the
    payload.
    """

    # S-1: inner subgraph node — ANONYMOUS. Caller trust is
    # authenticated once at the outer backbone (pre_process); inner nodes
    # must not re-demand a higher trust level.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        raw = state.get("user_input", "")
        try:
            payload = json.loads(raw) if isinstance(raw, str) else raw
        except (ValueError, TypeError):
            payload = None
        if not isinstance(payload, dict) or not payload.get("question"):
            emit_trace_event(
                "sensitive_content_minimization_rejected",
                {"correlation_id": state.get("correlation_id"), "reason": "missing_question"},
                state,
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["SensitiveContentMinimizationNode: missing 'question' in inner input"],
            }

        question = str(payload.get("question", ""))
        grant_program = str(payload.get("grant_program", "") or "")

        # Re-validate the outer QueryValidationNode's precondition: the outer
        # pre_process -> main edge is unconditional (fires even when
        # pre_process returned ERROR), so re-check the credential-pattern
        # rejection here too.
        if es.contains_credential_pattern(question):
            emit_trace_event(
                "sensitive_content_minimization_rejected",
                {"correlation_id": state.get("correlation_id"), "reason": "credential_pattern"},
                state,
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["SensitiveContentMinimizationNode: credential/Bearer/file-path pattern rejected"],
            }

        protected_query, masked_fields = es.minimize_sensitive_content(question)

        emit_trace_event(
            "sensitive_content_minimized",
            {"correlation_id": state.get("correlation_id"), "masked_field_count": len(masked_fields)},
            state,
        )
        return {
            "protected_query": protected_query,
            "grant_program": grant_program,
            "status": AgentStatus.SUCCESS.value,
        }
