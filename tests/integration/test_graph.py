# EDU-C2-076 — Integration test: full graph compile + invoke.

import json

from framework.schemas.agent_status import AgentStatus
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel

from src.graph.graph import Graph


class FakeLLM:
    def complete(self, *a, **k):
        return "eligible_indication"


class FakeRetriever:
    def search(self, query, filters, top_k):
        return [
            {
                "passage_id": "guideline-3-2",
                "text": "Applicants with prior sponsor funding in the current cycle remain eligible.",
                "score": 0.9,
                "verdict": "eligible",
                "addresses_criteria": True,
            }
        ]


class EmptyRetriever:
    def search(self, query, filters, top_k):
        return []


def _ctx(session="it-1"):
    return InvocationContext(session_id=session, caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="tester")


def _agent(retriever=None):
    a = Graph(config={"llm": FakeLLM(), "retriever": retriever, "max_retry": 1})
    a.compile()
    return a


def test_eligible_path_with_citation():
    payload = json.dumps({"question": "Am I eligible for JSPS given prior sponsor funding?", "grant_program": "jsps"})
    result = _agent(retriever=FakeRetriever()).invoke(payload, ctx=_ctx("it-eligible"))
    assert result["status"] in (AgentStatus.SUCCESS, AgentStatus.SUCCESS.value)
    nh = result.get("node_history") or []
    assert len(nh) >= 5, f"expected >=5 nodes, got {len(nh)}: {nh}"
    out = result.get("output") or {}
    assert out.get("answer_indication") == "eligible_indication"
    assert out.get("cited_passages")
    assert out.get("disclaimer")


def test_insufficient_information_path_no_retriever():
    payload = json.dumps({"question": "Am I eligible for AMED?", "grant_program": "amed"})
    result = _agent(retriever=EmptyRetriever()).invoke(payload, ctx=_ctx("it-insufficient"))
    assert result["status"] in (AgentStatus.SUCCESS, AgentStatus.SUCCESS.value)
    out = result.get("output") or {}
    assert out.get("answer_indication") == "insufficient_information"
    assert out.get("escalation_flag") is True
    assert out.get("review_status") == "pending_staff_review"


def test_empty_input_errors():
    result = _agent().invoke("", ctx=_ctx("it-empty"))
    assert result["status"] in (
        AgentStatus.ERROR, AgentStatus.ERROR.value, AgentStatus.CANCELLED, AgentStatus.CANCELLED.value,
    )


def test_credential_pattern_rejected():
    payload = json.dumps({"question": "Bearer sk-abcdefghijklmnopqrst am I eligible?"})
    result = _agent().invoke(payload, ctx=_ctx("it-cred"))
    assert result["status"] in (AgentStatus.ERROR, AgentStatus.ERROR.value)


def test_no_secret_in_output():
    payload = json.dumps({"question": "Am I eligible for JSPS?", "grant_program": "jsps"})
    result = _agent(retriever=FakeRetriever()).invoke(payload, ctx=_ctx("it-secret"))
    blob = json.dumps(result, default=str).lower()
    assert "sk-" not in blob and "eyj" not in blob
