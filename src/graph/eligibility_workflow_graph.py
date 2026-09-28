"""AgentCore Platform v1.0 — EDU-C2-076 inner eligibility workflow (Cat 2).

Instantiated by EligibilityGraphNode.get_subgraph(). Receives only the JSON
string user_input (seeded from the outer validated_input); the first inner
node reconstructs the payload.

Pipeline: sensitive_content_minimization -> guideline_version_selector ->
evidence_retriever -> eligibility_answer_draft -> escalation_rule ->
human_review_gate.
"""

from typing import Any
from langgraph.graph import END, START

from framework.graph.base_graph import BaseGraph
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus

from src.nodes.eligibility_answer_draft_node import EligibilityAnswerDraftNode
from src.nodes.escalation_rule_node import EscalationRuleNode
from src.nodes.evidence_retriever_node import EvidenceRetrieverNode
from src.nodes.guideline_version_selector_node import GuidelineVersionSelectorNode
from src.nodes.human_review_gate_node import HumanReviewGateNode
from src.nodes.sensitive_content_minimization_node import SensitiveContentMinimizationNode
from src.schemas.state import State


class EligibilityWorkflowGraph(BaseGraph):
    """Inner multi-step grant-eligibility evidence workflow."""

    @property
    def name(self) -> str:
        return "edu_c2_076_eligibility_workflow"

    @property
    def state_schema(self) -> type:
        return State

    def _validate_config(self) -> None:
        pass

    def register_nodes(self) -> None:
        llm = self.config.get("llm") if hasattr(self, "config") else None
        retriever = self.config.get("retriever") if hasattr(self, "config") else None
        top_k = self.config.get("top_k", 5) if hasattr(self, "config") else 5
        confidence_threshold = self.config.get("confidence_threshold", 0.6) if hasattr(self, "config") else 0.6
        self._nodes["sensitive_content_minimization"] = SensitiveContentMinimizationNode()
        self._nodes["guideline_version_selector"] = GuidelineVersionSelectorNode()
        self._nodes["evidence_retriever"] = EvidenceRetrieverNode(retriever=retriever, top_k=top_k)
        self._nodes["eligibility_answer_draft"] = EligibilityAnswerDraftNode(
            llm=llm, confidence_threshold=confidence_threshold
        )
        self._nodes["escalation_rule"] = EscalationRuleNode(confidence_threshold=confidence_threshold)
        self._nodes["human_review_gate"] = HumanReviewGateNode()

    def add_edges(self) -> None:
        self._sg.add_edge(START, "sensitive_content_minimization")
        self._sg.add_edge("sensitive_content_minimization", "guideline_version_selector")
        self._sg.add_edge("guideline_version_selector", "evidence_retriever")
        self._sg.add_edge("evidence_retriever", "eligibility_answer_draft")
        self._sg.add_edge("eligibility_answer_draft", "escalation_rule")
        self._sg.add_edge("escalation_rule", "human_review_gate")
        self._sg.add_edge("human_review_gate", END)

    def route(self, state: AgentState) -> str:
        # Required by ABC; this topology is linear so route() is never invoked
        # (no add_conditional_edges() calls it).
        return END if state.get("status") == AgentStatus.ERROR.value else "human_review_gate"

    def get_output(self, state: AgentState) -> dict[str, Any]:
        return {
            "protected_query": state.get("protected_query", ""),
            "kb_version": state.get("kb_version", ""),
            "retrieved_passages": state.get("retrieved_passages", []),
            "retrieval_confidence": state.get("retrieval_confidence", 0.0),
            "answer_indication": state.get("answer_indication", ""),
            "cited_passages": state.get("cited_passages", []),
            "assumptions": state.get("assumptions", []),
            "escalation_flag": state.get("escalation_flag", False),
            "escalation_condition": state.get("escalation_condition", ""),
            "review_status": state.get("review_status", ""),
            "status": state.get("status"),
            "trace_id": state.get("trace_id"),
            "correlation_id": state.get("correlation_id"),
            "node_history": state.get("node_history", []),
        }
