# EDU-C2-076 — Unit tests (per node: success + error/edge).

import json

from framework.schemas.agent_status import AgentStatus

from src.nodes.eligibility_answer_draft_node import EligibilityAnswerDraftNode
from src.nodes.escalation_rule_node import EscalationRuleNode
from src.nodes.evidence_retriever_node import EvidenceRetrieverNode
from src.nodes.guideline_version_selector_node import GuidelineVersionSelectorNode
from src.nodes.human_review_gate_node import HumanReviewGateNode
from src.nodes.query_validation_node import QueryValidationNode
from src.nodes.secure_output_node import SecureOutputNode
from src.nodes.sensitive_content_minimization_node import SensitiveContentMinimizationNode
from src.services import eligibility_service as es


def _s(**kw):
    st = {"node_history": [], "error_log": [], "execution_time": {}, "correlation_id": "c"}
    st.update(kw)
    return st


class TestQueryValidationNode:
    def setup_method(self):
        self.node = QueryValidationNode()

    def test_success(self):
        p = json.dumps({"question": "Is my JSPS proposal eligible?", "grant_program": "jsps"})
        r = self.node.execute(_s(user_input=p))
        assert r["status"] == AgentStatus.SUCCESS
        assert r["grant_program"] == "jsps"

    def test_empty(self):
        assert self.node.execute(_s(user_input=""))["status"] == AgentStatus.ERROR

    def test_missing_question(self):
        p = json.dumps({"grant_program": "jsps"})
        assert self.node.execute(_s(user_input=p))["status"] == AgentStatus.ERROR

    def test_rejects_credential_pattern(self):
        p = json.dumps({"question": "Bearer sk-abcdefghijklmnopqrst eligibility?"})
        assert self.node.execute(_s(user_input=p))["status"] == AgentStatus.ERROR

    def test_rejects_unknown_grant_program(self):
        p = json.dumps({"question": "Am I eligible?", "grant_program": "not-a-real-program"})
        assert self.node.execute(_s(user_input=p))["status"] == AgentStatus.ERROR

    def test_plain_text_input(self):
        r = self.node.execute(_s(user_input="Am I eligible for AMED funding?"))
        assert r["status"] == AgentStatus.SUCCESS


class TestSensitiveContentMinimizationNode:
    def setup_method(self):
        self.node = SensitiveContentMinimizationNode()

    def test_success(self):
        inner = json.dumps({"question": "Is my proposal eligible?", "grant_program": "jsps"})
        r = self.node.execute(_s(user_input=inner))
        assert r["status"] == AgentStatus.SUCCESS
        assert "REDACTED" not in r["protected_query"]

    def test_masks_sensitive_markers(self):
        inner = json.dumps({"question": "applicant_id 12345 eligibility check", "grant_program": "jsps"})
        r = self.node.execute(_s(user_input=inner))
        assert r["status"] == AgentStatus.SUCCESS
        assert "[REDACTED]" in r["protected_query"]

    def test_missing_question(self):
        assert self.node.execute(_s(user_input=json.dumps({})))["status"] == AgentStatus.ERROR


class TestGuidelineVersionSelectorNode:
    def setup_method(self):
        self.node = GuidelineVersionSelectorNode()

    def test_success(self):
        r = self.node.execute(_s(grant_program="jsps"))
        assert r["status"] == AgentStatus.SUCCESS
        assert r["kb_version"]

    def test_upstream_error_short_circuits(self):
        assert self.node.execute(_s(status=AgentStatus.ERROR))["status"] == AgentStatus.ERROR


class TestEvidenceRetrieverNode:
    def test_no_retriever_yields_empty(self):
        node = EvidenceRetrieverNode()
        r = node.execute(_s(protected_query="q", kb_version="v1"))
        assert r["status"] == AgentStatus.SUCCESS
        assert r["retrieved_passages"] == []
        assert r["retrieval_confidence"] == 0.0

    def test_with_retriever(self):
        class FakeRetriever:
            def search(self, query, filters, top_k):
                return [{"passage_id": "p1", "text": "eligible if...", "score": 0.9, "verdict": "eligible", "addresses_criteria": True}]

        node = EvidenceRetrieverNode(retriever=FakeRetriever())
        r = node.execute(_s(protected_query="q", kb_version="v1"))
        assert r["status"] == AgentStatus.SUCCESS
        assert len(r["retrieved_passages"]) == 1
        assert r["retrieval_confidence"] == 0.9

    def test_upstream_error_short_circuits(self):
        node = EvidenceRetrieverNode()
        assert node.execute(_s(status=AgentStatus.ERROR))["status"] == AgentStatus.ERROR


class TestEligibilityAnswerDraftNode:
    def test_low_confidence_is_insufficient(self):
        node = EligibilityAnswerDraftNode()
        r = node.execute(_s(retrieved_passages=[{"passage_id": "p1", "addresses_criteria": True, "verdict": "eligible"}], retrieval_confidence=0.1))
        assert r["answer_indication"] == es.INSUFFICIENT

    def test_confident_eligible(self):
        node = EligibilityAnswerDraftNode()
        passages = [{"passage_id": "p1", "addresses_criteria": True, "verdict": "eligible", "text": "span"}]
        r = node.execute(_s(retrieved_passages=passages, retrieval_confidence=0.9))
        assert r["answer_indication"] == es.ELIGIBLE
        assert r["cited_passages"]

    def test_no_passages_is_insufficient(self):
        node = EligibilityAnswerDraftNode()
        r = node.execute(_s(retrieved_passages=[], retrieval_confidence=0.9))
        assert r["answer_indication"] == es.INSUFFICIENT

    def test_upstream_error_short_circuits(self):
        node = EligibilityAnswerDraftNode()
        assert node.execute(_s(status=AgentStatus.ERROR))["status"] == AgentStatus.ERROR

    def test_llm_canonical_dict_response_is_consumed(self):
        """3m: BaseLLM.complete() returns {"content": str, ...} — must be
        extracted, not str()-ed whole, or the suggestion never matches
        VALID_INDICATIONS and is silently discarded."""

        class DictLLM:
            def complete(self, messages):
                return {"content": "eligible_indication", "model": "fake", "usage": {}}

        node = EligibilityAnswerDraftNode(llm=DictLLM())
        passages = [{"passage_id": "p1", "addresses_criteria": True, "text": "span"}]
        r = node.execute(_s(retrieved_passages=passages, retrieval_confidence=0.9))
        assert r["answer_indication"] == es.ELIGIBLE

    def test_llm_bare_string_response_backward_compat(self):
        class StringLLM:
            def complete(self, messages):
                return "eligible_indication"

        node = EligibilityAnswerDraftNode(llm=StringLLM())
        passages = [{"passage_id": "p1", "addresses_criteria": True, "text": "span"}]
        r = node.execute(_s(retrieved_passages=passages, retrieval_confidence=0.9))
        assert r["answer_indication"] == es.ELIGIBLE

    def test_llm_failure_degrades_to_deterministic_path(self):
        class RaisingLLM:
            def complete(self, messages):
                raise RuntimeError("provider down")

        node = EligibilityAnswerDraftNode(llm=RaisingLLM())
        passages = [{"passage_id": "p1", "addresses_criteria": True, "verdict": "eligible", "text": "span"}]
        r = node.execute(_s(retrieved_passages=passages, retrieval_confidence=0.9))
        assert r["status"] == AgentStatus.SUCCESS.value
        assert r["answer_indication"] == es.ELIGIBLE


class TestEscalationRuleNode:
    def test_insufficient_escalates(self):
        node = EscalationRuleNode()
        r = node.execute(_s(answer_indication=es.INSUFFICIENT, retrieved_passages=[], retrieval_confidence=0.1))
        assert r["escalation_flag"] is True
        assert r["escalation_condition"]

    def test_confident_eligible_no_escalation(self):
        node = EscalationRuleNode()
        passages = [{"passage_id": "p1", "addresses_criteria": True, "verdict": "eligible"}]
        r = node.execute(_s(answer_indication=es.ELIGIBLE, retrieved_passages=passages, retrieval_confidence=0.9))
        assert r["escalation_flag"] is False


class TestHumanReviewGateNode:
    def test_escalated_pending_review(self):
        node = HumanReviewGateNode()
        r = node.execute(_s(escalation_flag=True))
        assert r["review_status"] == "pending_staff_review"

    def test_not_escalated_auto_cleared(self):
        node = HumanReviewGateNode()
        r = node.execute(_s(escalation_flag=False))
        assert r["review_status"] == "auto_cleared"


class TestSecureOutputNode:
    def setup_method(self):
        self.node = SecureOutputNode()

    def test_insufficient_answer(self):
        r = self.node.execute(_s(answer_indication=es.INSUFFICIENT, cited_passages=[], escalation_flag=True))
        assert r["status"] == AgentStatus.SUCCESS
        assert "Insufficient" in r["answer_text"]

    def test_eligible_with_citation(self):
        claims = [{"result_id": "draft-0", "source_passage_id": "p1", "source_span": "span text"}]
        r = self.node.execute(_s(answer_indication=es.ELIGIBLE, cited_passages=claims, escalation_flag=False))
        assert r["status"] == AgentStatus.SUCCESS
        assert "Eligible" in r["answer_text"]

    def test_execute_blocks_missing_citation(self):
        r = self.node.execute(_s(answer_indication=es.ELIGIBLE, cited_passages=[]))
        assert r["status"] == AgentStatus.ERROR

    def test_execute_blocks_incomplete_claim(self):
        claims = [{"result_id": "draft-0"}]
        r = self.node.execute(_s(answer_indication=es.ELIGIBLE, cited_passages=claims))
        assert r["status"] == AgentStatus.ERROR

    def test_output_gate_hook_blocks_insufficient_rendered_resolved(self):
        # The hook receives execute()'s own partial return (not the full outer
        # state) — self-consistency check against the co-located formatted_output.
        r = self.node._extra_security_gate_output(
            {
                "answer_text": "Eligible indication based on...",
                "formatted_output": {"answer_indication": es.INSUFFICIENT},
            }
        )
        assert r["status"] == AgentStatus.ERROR

    def test_output_gate_hook_passthrough_when_consistent(self):
        claims = [{"result_id": "draft-0", "source_passage_id": "p1", "source_span": "span text"}]
        executed = self.node.execute(_s(answer_indication=es.ELIGIBLE, cited_passages=claims, escalation_flag=False))
        r = self.node._extra_security_gate_output(executed)
        assert r.get("status") == AgentStatus.SUCCESS

    def test_upstream_error_short_circuits(self):
        assert self.node.execute(_s(status=AgentStatus.ERROR))["status"] == AgentStatus.ERROR
