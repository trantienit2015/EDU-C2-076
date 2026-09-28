"""AgentCore Platform v1.0 — outer post_process: SecureOutputNode (S-3 gate)."""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services import eligibility_service as es


class SecureOutputNode(FunctionNode):
    """S-3 deterministic output gate (Step 8).

    Every rendered answer must carry a structured evidence claim (cited
    passage id + verbatim source span) drawn from the retrieved set. Render
    answer text ONLY from these locked claims (no free-form eligibility
    assertion). Gate behavior: any claim missing a citation, or an
    insufficient_information case rendered as a resolved eligibility answer
    -> FAIL THE WHOLE PACKAGE (never drop-and-continue); on catch -> log audit.

    The substantive validation runs inside execute() (which has full access
    to upstream state); the non-suppressible _extra_security_gate_output()
    hook only re-checks the *self-consistency of its own returned dict*
    (framework invokes it with execute()'s partial return, not the full
    merged state — re-deriving from separate state.get() fields there is
    fragile and produces false positives).
    """

    # S-1: outer boundary node — matches agent.yaml required_trust_level.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        if es.is_upstream_error(state.get("status")):
            emit_trace_event(
                "output_skipped_upstream_error",
                {"correlation_id": state.get("correlation_id")},
                state,
            )
            return {"status": AgentStatus.ERROR.value}

        answer_indication = state.get("answer_indication", es.INSUFFICIENT)
        cited_passages = state.get("cited_passages", []) or []
        escalation_flag = bool(state.get("escalation_flag", False))
        escalation_condition = state.get("escalation_condition", "")
        review_status = state.get("review_status", "auto_cleared")

        # Structured-evidence-claim gate (Step 8) — validated
        # here where the full upstream state is available, not in the hook.
        if answer_indication in (es.ELIGIBLE, es.INELIGIBLE) and not cited_passages:
            emit_trace_event(
                "output_gate_rejected",
                {"correlation_id": state.get("correlation_id"), "reason": "missing_evidence_claim"},
                state,
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["SecureOutputNode: resolved eligibility answer missing structured evidence claim"],
            }
        for claim in cited_passages:
            if not claim.get("result_id") or not claim.get("source_passage_id") or not claim.get("source_span"):
                emit_trace_event(
                    "output_gate_rejected",
                    {"correlation_id": state.get("correlation_id"), "reason": "incomplete_evidence_claim"},
                    state,
                )
                return {
                    "status": AgentStatus.ERROR.value,
                    "error_log": ["SecureOutputNode: evidence claim missing result-ID/source-passage/source-span"],
                }

        answer_text = self._render_answer_text(answer_indication, cited_passages, escalation_flag)

        emit_trace_event(
            "output_gated",
            {"correlation_id": state.get("correlation_id"), "answer_indication": answer_indication},
            state,
        )
        return {
            "answer_text": answer_text,
            "disclaimer": es.DISCLAIMER,
            "formatted_output": {
                "answer_indication": answer_indication,
                "answer_text": answer_text,
                "cited_passages": cited_passages,
                "assumptions": state.get("assumptions", []),
                "escalation_condition": escalation_condition,
                "escalation_flag": escalation_flag,
                "review_status": review_status,
                "disclaimer": es.DISCLAIMER,
                "confidence": state.get("retrieval_confidence", 0.0),
            },
            "status": AgentStatus.SUCCESS.value,
        }

    @staticmethod
    def _render_answer_text(answer_indication: str, cited_passages: list[dict[str, Any]], escalation_flag: bool) -> str:
        if answer_indication == es.INSUFFICIENT:
            return "Insufficient information to indicate eligibility — escalated for staff confirmation."
        prefix = "Eligible indication" if answer_indication == es.ELIGIBLE else "Ineligible indication"
        refs = ", ".join(f"[{p.get('result_id', '?')}]" for p in cited_passages)
        suffix = " (pending staff confirmation)" if escalation_flag else ""
        return f"{prefix} based on cited guidance {refs}{suffix}."

    def _extra_security_gate_output(self, state: dict[str, Any]) -> dict[str, Any]:
        """S-3 non-suppressible re-check (framework-invoked with execute()'s
        return value; never raises). Checks self-consistency of the rendered
        answer_text against the co-located formatted_output.answer_indication
        in the SAME dict — does not re-derive from separate outer state keys
        (those are not guaranteed present on this call)."""
        answer_text = state.get("answer_text", "") or ""
        formatted_output = state.get("formatted_output") or {}
        answer_indication = formatted_output.get("answer_indication", "")

        if answer_indication == es.INSUFFICIENT and (
            answer_text.startswith("Eligible indication") or answer_text.startswith("Ineligible indication")
        ):
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["SecureOutputNode: insufficient_information rendered as a resolved answer"],
            }
        return state
