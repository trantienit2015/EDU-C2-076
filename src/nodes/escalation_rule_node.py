"""AgentCore Platform v1.0 — inner step 5: escalation rule."""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services import eligibility_service as es


class EscalationRuleNode(FunctionNode):
    """Escalate exceptions, conflicts, or missing evidence to grant staff
    (Step 6). Deterministic — no LLM.
    """

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def __init__(self, confidence_threshold: float = es.DEFAULT_CONFIDENCE_THRESHOLD):
        self._confidence_threshold = confidence_threshold

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        if es.is_upstream_error(state.get("status")):
            emit_trace_event(
                "escalation_evaluation_skipped_upstream_error",
                {"correlation_id": state.get("correlation_id")},
                state,
            )
            return {"status": AgentStatus.ERROR.value}

        answer_indication = state.get("answer_indication", es.INSUFFICIENT)
        passages = state.get("retrieved_passages", []) or []
        confidence = float(state.get("retrieval_confidence", 0.0))

        escalation_flag, escalation_condition = es.needs_escalation(
            answer_indication, passages, confidence, self._confidence_threshold
        )

        emit_trace_event(
            "escalation_evaluated",
            {"correlation_id": state.get("correlation_id"), "escalation_flag": escalation_flag},
            state,
        )
        return {
            "escalation_flag": escalation_flag,
            "escalation_condition": escalation_condition,
            "status": AgentStatus.SUCCESS.value,
        }
