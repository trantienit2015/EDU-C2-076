"""AgentCore Platform v1.0 — outer pre_process: QueryValidationNode (S-1 + S-2)."""

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services import eligibility_service as es

MAX_INPUT_CHARS = 100_000


class QueryValidationNode(FunctionNode):
    """S-1 trust gate + S-2 deterministic input scan.

    Accepts a JSON payload: {"question": "<text>", "grant_program": "<id>"}.
    Plain-text input (not JSON) is treated as the question with no program
    selected. Rejects credential/Bearer/file-path-shaped strings via a
    fail-closed ERROR (deterministic scan — NOT an LLM check); validates the
    selected grant program; passes clean questions through unchanged.
    """

    # S-1: outer boundary node — matches agent.yaml required_trust_level.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        raw = state.get("user_input", "")
        emit_trace_event(
            "query_validation_started",
            {"correlation_id": state.get("correlation_id")},
            state,
        )
        if not isinstance(raw, str) or not raw.strip():
            return {"status": AgentStatus.ERROR.value, "error_log": ["QueryValidationNode: empty input"]}
        if len(raw) > MAX_INPUT_CHARS:
            return {"status": AgentStatus.ERROR.value, "error_log": ["QueryValidationNode: input too large"]}

        # S-2 deterministic scan — credential/Bearer/file-path patterns rejected
        # before any downstream processing, regardless of payload shape.
        if es.contains_credential_pattern(raw):
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["QueryValidationNode: credential/Bearer/file-path pattern rejected"],
            }

        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                payload = {"question": raw}
        except (ValueError, TypeError):
            payload = {"question": raw}

        question = str(payload.get("question", "") or "")
        grant_program = str(payload.get("grant_program", "") or "")

        if not question.strip():
            return {"status": AgentStatus.ERROR.value, "error_log": ["QueryValidationNode: 'question' is required"]}

        if grant_program and not es.is_valid_grant_program(grant_program):
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [f"QueryValidationNode: unknown grant_program '{grant_program}'"],
            }

        normalized = {"question": question, "grant_program": grant_program}
        return {
            "grant_program": grant_program,
            "validated_input": json.dumps(normalized, ensure_ascii=False),
            "status": AgentStatus.SUCCESS.value,
        }
