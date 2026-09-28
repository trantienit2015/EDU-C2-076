# PB-6 supplement: GraphNode boundary coverage.
# EligibilityGraphNode lives in src/graph/graph.py (not src/nodes/), by design,
# so it is outside PB-6's discovery scope (test_pb_invoke_order.py only walks
# src.nodes.*). That placement is correct (matches scaffold canonical Cat 2
# pattern) but does not exempt the outer main-slot node from boundary
# coverage — it is the first node to receive caller input in the outer
# backbone. This module fills that gap:
#   - S-1 trust gate rejects an under-privileged caller before execute() runs
#   - extract_input()/merge_output() map fields explicitly (criterion #9),
#     no raw subgraph-result pass-through
#   - inner subgraph entry point (SensitiveContentMinimizationNode) carries
#     its own S-2 content-scan — GraphNode delegates gating there by design
#     (framework/nodes/graph_node.py: execute() calls subgraph.invoke(),
#     which runs each inner node's own __call__ S-1/S-2/S-3 lifecycle).

from framework.schemas.trust_level import TrustLevel

from src.graph.graph import EligibilityGraphNode
from src.nodes.sensitive_content_minimization_node import SensitiveContentMinimizationNode


class TestGraphNodeS1TrustGate:
    """S-1: __call__ (BaseNode, never overridden) must deny an under-privileged
    caller before execute()/get_subgraph() runs."""

    def test_denies_anonymous_caller(self, monkeypatch):
        node = EligibilityGraphNode()
        assert node.required_trust_level == TrustLevel.VERIFIED_EXTERNAL

        def _boom():
            raise AssertionError("get_subgraph() must not run — S-1 gate should short-circuit")

        monkeypatch.setattr(node, "get_subgraph", _boom)

        result = node({"caller_trust_level": TrustLevel.ANONYMOUS.value})

        assert result["status"] == "error"
        assert any("S-1 trust gate denied" in e for e in result["error_log"])

    def test_allows_verified_external_caller(self, monkeypatch):
        node = EligibilityGraphNode()

        class _StubSubgraph:
            name = "stub"

            def invoke(self, user_input, session_id=None, ctx=None):
                return {"status": "success", "answer_indication": "insufficient_information"}

        monkeypatch.setattr(node, "get_subgraph", lambda: _StubSubgraph())

        result = node(
            {
                "caller_trust_level": TrustLevel.VERIFIED_EXTERNAL.value,
                "session_id": "sess-1",
                "thread_id": "thread-1",
                "trace_id": "trace-1",
                "correlation_id": "corr-1",
                "validated_input": '{"question": "q", "grant_program": ""}',
            }
        )
        assert result["status"] == "success"


class TestGraphNodeBoundaryMapping:
    """extract_input()/merge_output() must map fields explicitly (criterion #9) —
    no raw pass-through of caller state or subgraph result dicts."""

    def test_extract_input_only_forwards_validated_input(self):
        node = EligibilityGraphNode()
        state = {
            "validated_input": '{"question": "q", "grant_program": "p1"}',
            "secret_field": "must-not-leak",
            "correlation_id": "corr-2",
        }
        extracted = node.extract_input(state)
        assert extracted == state["validated_input"]
        assert "must-not-leak" not in extracted

    def test_merge_output_maps_known_fields_only(self):
        node = EligibilityGraphNode()
        sub_result = {
            "protected_query": "masked question",
            "kb_version": "v1",
            "retrieved_passages": [{"passage_id": "p1"}],
            "retrieval_confidence": 0.9,
            "answer_indication": "eligible_indication",
            "cited_passages": [],
            "assumptions": [],
            "escalation_flag": False,
            "escalation_condition": "",
            "review_status": "auto_cleared",
            "status": "success",
            "internal_debug_dump": {"should": "not leak"},
        }
        merged = node.merge_output({"correlation_id": "corr-3"}, sub_result)
        assert "internal_debug_dump" not in merged
        assert merged["answer_indication"] == "eligible_indication"
        assert merged["kb_version"] == "v1"
        assert merged["status"] == "success"


class TestInnerEntryDelegatesGatingByDesign:
    """GraphNode.execute() (framework/nodes/graph_node.py) delegates S-2/S-3
    gating to the inner subgraph's own node lifecycle — it does not run the
    outer FunctionNode gate hooks itself. Verify the inner entry node
    (SensitiveContentMinimizationNode) carries its own content-scan so the
    boundary is not silently ungated."""

    def test_inner_entry_node_is_anonymous_and_scans_content(self):
        assert SensitiveContentMinimizationNode.required_trust_level == TrustLevel.ANONYMOUS

        node = SensitiveContentMinimizationNode()
        result = node.execute(
            {"user_input": '{"question": "Bearer abc.def.ghi", "grant_program": ""}'}
        )
        assert result["status"] == "error"
        assert any("credential" in e.lower() for e in result["error_log"])
