"""AgentCore Platform v1.0 — inner step 6: human review gate."""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event


class HumanReviewGateNode(FunctionNode):
    """Never makes the final decision; requires staff confirmation for
    flagged cases (Step 7).

    This is a synchronous administrative Q&A (not a paused HITL flow): the
    gate marks ``review_status`` so the rendered answer is labeled
    "pending staff confirmation" when escalated, rather than pausing the
    graph via interrupt(). The university/sponsor retains final authority
    regardless of review_status (see docs/02_design.md).
    """

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        if str(state.get("status", "")).lower().endswith("error"):
            emit_trace_event(
                "human_review_gate_skipped_upstream_error",
                {"correlation_id": state.get("correlation_id")},
                state,
            )
            return {"status": AgentStatus.ERROR.value}

        escalation_flag = bool(state.get("escalation_flag", False))
        review_status = "pending_staff_review" if escalation_flag else "auto_cleared"

        emit_trace_event(
            "human_review_gated",
            {"correlation_id": state.get("correlation_id"), "review_status": review_status},
            state,
        )
        return {"review_status": review_status, "status": AgentStatus.SUCCESS.value}
