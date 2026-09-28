"""AgentCore Platform v1.0 — inner step 3: evidence retrieval."""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services import eligibility_service as es


class EvidenceRetrieverNode(FunctionNode):
    """Dense (+optional hybrid) retrieval with page/section metadata filter,
    multilingual-e5 embedding, top_k @ config.

    ``retriever`` is injected (search(query, filters, top_k) -> list[dict]);
    falls back to an empty result set when unset (deterministic no-op —
    downstream fail-safe rule then returns insufficient_information).
    """

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def __init__(self, retriever: Any = None, top_k: int = 5):
        self._retriever = retriever
        self._top_k = top_k

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        if es.is_upstream_error(state.get("status")):
            emit_trace_event(
                "evidence_retrieval_skipped_upstream_error",
                {"correlation_id": state.get("correlation_id")},
                state,
            )
            return {"status": AgentStatus.ERROR.value}

        protected_query = state.get("protected_query", "")
        kb_version = state.get("kb_version", "")

        passages: list[dict[str, Any]] = []
        if self._retriever is not None:
            try:
                passages = (
                    self._retriever.search(protected_query, filters={"kb_version": kb_version}, top_k=self._top_k) or []
                )
            except Exception as exc:  # noqa: BLE001 — degrade to empty result, never raise
                import logging

                logging.getLogger(__name__).warning("evidence retrieval failed: %s", exc)
                passages = []

        confidence = es.aggregate_retrieval_confidence(passages)

        emit_trace_event(
            "evidence_retrieved",
            {"correlation_id": state.get("correlation_id"), "n_passages": len(passages)},
            state,
        )
        return {
            "retrieved_passages": passages,
            "retrieval_confidence": confidence,
            "status": AgentStatus.SUCCESS.value,
        }
