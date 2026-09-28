"""AgentCore Platform v1.0 — EDU-C2-076 outer graph (Cat 2).

Outer (AgentBaseGraph): initialize -> pre_process(QueryValidationNode) ->
main(EligibilityGraphNode) -> post_process(SecureOutputNode) -> finalize.
Inner (BaseGraph): sensitive_content_minimization -> guideline_version_selector
-> evidence_retriever -> eligibility_answer_draft -> escalation_rule ->
human_review_gate.

The GraphNode wrapper is colocated with the outer Graph class in THIS file
(not src/nodes/) because it is part of the outer backbone composition, not a
standalone leaf node — see tests/proof_of_boundary/test_pb_graphnode_boundary.py
for its dedicated boundary coverage.
"""

from typing import Any, ClassVar, cast

from framework.graph.agent_base_graph import AgentBaseGraph
from framework.nodes.graph_node import GraphNode
from framework.schemas.agent_state import AgentState
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.nodes.query_validation_node import QueryValidationNode
from src.nodes.secure_output_node import SecureOutputNode
from src.schemas.state import State


class EligibilityGraphNode(GraphNode):
    """Wraps the inner grant-eligibility evidence workflow (main slot)."""

    # S-1: outer boundary node — matches agent.yaml required_trust_level.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL
    error_strategy: ClassVar[str] = "propagate"
    propagate_hitl: ClassVar[bool] = False

    def __init__(self, llm: Any = None, retriever: Any = None, top_k: int = 5, confidence_threshold: float = 0.6):
        super().__init__()
        self._llm = llm
        self._retriever = retriever
        self._top_k = top_k
        self._confidence_threshold = confidence_threshold

    def get_subgraph(self) -> Any:
        from src.graph.eligibility_workflow_graph import EligibilityWorkflowGraph

        sg = EligibilityWorkflowGraph(config=self._parent_config())
        sg.compile()
        return sg

    def extract_input(self, state: AgentState) -> str:
        emit_trace_event(
            "eligibility_workflow_dispatched",
            {"correlation_id": state.get("correlation_id")},
            state,
        )
        return cast(str, state.get("validated_input", state.get("user_input", "")))

    def merge_output(self, state: AgentState, sub_result: dict[str, Any]) -> dict[str, Any]:
        emit_trace_event(
            "eligibility_workflow_completed",
            {"correlation_id": state.get("correlation_id"), "answer_indication": sub_result.get("answer_indication")},
            state,
        )
        return {
            "protected_query": sub_result.get("protected_query", ""),
            "kb_version": sub_result.get("kb_version", ""),
            "retrieved_passages": sub_result.get("retrieved_passages", []),
            "retrieval_confidence": sub_result.get("retrieval_confidence", 0.0),
            "answer_indication": sub_result.get("answer_indication", ""),
            "cited_passages": sub_result.get("cited_passages", []),
            "assumptions": sub_result.get("assumptions", []),
            "escalation_flag": sub_result.get("escalation_flag", False),
            "escalation_condition": sub_result.get("escalation_condition", ""),
            "review_status": sub_result.get("review_status", ""),
            "status": sub_result.get("status"),
        }

    def _parent_config(self) -> dict[str, Any]:
        return {
            "llm": self._llm,
            "retriever": self._retriever,
            "top_k": self._top_k,
            "confidence_threshold": self._confidence_threshold,
        }


class Graph(AgentBaseGraph):
    """EDU-C2-076 — University Research-Grant Eligibility Evidence Q&A Agent."""

    @property
    def name(self) -> str:
        return "edu-c2-076"

    @property
    def state_schema(self) -> type:
        return State

    def register_nodes(self) -> None:
        super().register_nodes()
        llm = self.config.get("llm") if hasattr(self, "config") else None
        retriever = self.config.get("retriever") if hasattr(self, "config") else None
        top_k = self.config.get("top_k", 5) if hasattr(self, "config") else 5
        confidence_threshold = self.config.get("confidence_threshold", 0.6) if hasattr(self, "config") else 0.6
        self._nodes["pre_process"] = QueryValidationNode()
        self._nodes["main"] = EligibilityGraphNode(
            llm=llm, retriever=retriever, top_k=top_k, confidence_threshold=confidence_threshold
        )
        self._nodes["post_process"] = SecureOutputNode()

    # add_edges() is NOT overridden — backbone wiring belongs to the framework.
