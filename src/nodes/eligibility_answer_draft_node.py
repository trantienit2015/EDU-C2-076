"""AgentCore Platform v1.0 — inner step 4: eligibility answer draft."""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services import eligibility_service as es


class EligibilityAnswerDraftNode(FunctionNode):
    """Draft an eligibility indication grounded in retrieved passages
    (Step 5).

    Status vocabulary (3 levels): eligible_indication / ineligible_indication
    / insufficient_information. Fail-safe default: low retrieval confidence,
    no passage directly addressing the applicant's stated criteria, or
    conflicting guideline passages -> ALWAYS insufficient_information (never
    force eligible/ineligible on ambiguous or low-confidence retrieval). LLM
    drafting is explanatory only; the deterministic confidence-threshold rule
    decides the final status.
    """

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def __init__(self, llm: Any = None, confidence_threshold: float = es.DEFAULT_CONFIDENCE_THRESHOLD):
        self._llm = llm
        self._confidence_threshold = confidence_threshold

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        if es.is_upstream_error(state.get("status")):
            emit_trace_event(
                "eligibility_answer_draft_skipped_upstream_error",
                {"correlation_id": state.get("correlation_id")},
                state,
            )
            return {"status": AgentStatus.ERROR.value}

        passages = state.get("retrieved_passages", []) or []
        confidence = float(state.get("retrieval_confidence", 0.0))

        llm_suggested = self._llm_suggest(state.get("protected_query", ""), passages)
        answer_indication = es.decide_answer_indication(passages, confidence, self._confidence_threshold, llm_suggested)

        cited_passages = []
        assumptions: list[str] = []
        if answer_indication in (es.ELIGIBLE, es.INELIGIBLE):
            cited_passages = [
                {
                    "result_id": f"draft-{i}",
                    "source_passage_id": p.get("passage_id", f"p{i}"),
                    "source_span": p.get("text", ""),
                }
                for i, p in enumerate(passages)
                if p.get("addresses_criteria")
            ]
        else:
            assumptions.append("Retrieval confidence or evidence coverage insufficient for a resolved indication.")

        emit_trace_event(
            "eligibility_answer_drafted",
            {"correlation_id": state.get("correlation_id"), "answer_indication": answer_indication},
            state,
        )
        return {
            "answer_indication": answer_indication,
            "cited_passages": cited_passages,
            "assumptions": assumptions,
            "status": AgentStatus.SUCCESS.value,
        }

    def _llm_suggest(self, query: str, passages: list[dict[str, Any]]) -> str | None:
        """LLM drafting is explanatory only — never authoritative (fail-safe
        deterministic rule in es.decide_answer_indication always wins on
        low confidence / conflict / missing coverage)."""
        if self._llm is None:
            return None
        try:
            note = self._llm.complete(
                [
                    {
                        "role": "user",
                        "content": f"Draft an eligibility indication ({es.VALID_INDICATIONS}) for: {query[:500]}",
                    }
                ]
            )
            suggestion = self._extract_text(note).strip().lower()
            return suggestion if suggestion in es.VALID_INDICATIONS else None
        except Exception as exc:  # noqa: BLE001 — degrade to deterministic-only path
            import logging

            logging.getLogger(__name__).warning("eligibility answer draft LLM suggest failed: %s", exc)
            return None

    @staticmethod
    def _extract_text(raw: Any) -> str:
        """Normalize BaseLLM.complete() response (canonical dict {"content": str, ...}
        or a bare string from test/legacy fakes) before any string ops (3m)."""
        if isinstance(raw, dict):
            content = raw.get("content", "")
            return content if isinstance(content, str) else ""
        if isinstance(raw, str):
            return raw
        return ""
