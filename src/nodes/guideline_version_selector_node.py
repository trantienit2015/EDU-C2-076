"""AgentCore Platform v1.0 — inner step 2: guideline version selection."""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services import eligibility_service as es


class GuidelineVersionSelectorNode(FunctionNode):
    """Select the administrator-approved guideline version (Step 3).
    Deterministic — no LLM.
    """

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        if es.is_upstream_error(state.get("status")):
            emit_trace_event(
                "guideline_version_selection_skipped_upstream_error",
                {"correlation_id": state.get("correlation_id")},
                state,
            )
            return {"status": AgentStatus.ERROR.value}

        grant_program = state.get("grant_program", "")
        kb_version = es.select_guideline_version(grant_program)

        emit_trace_event(
            "guideline_version_selected",
            {"correlation_id": state.get("correlation_id"), "kb_version": kb_version},
            state,
        )
        return {"kb_version": kb_version, "status": AgentStatus.SUCCESS.value}
