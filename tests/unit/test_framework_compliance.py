# EDU-C2-076 - Framework compliance tests TC-01..TC-08.
# Adapted to this template's real architecture (Cat 2: outer QueryValidationNode pre_process +
# GraphNode-wrapped inner sensitive_content_minimization/guideline_version_selector/
# evidence_retriever/eligibility_answer_draft/escalation_rule/human_review_gate +
# SecureOutputNode post_process).

import json
import os
import re

import pytest
from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel

from src.nodes import (
    eligibility_answer_draft_node,
    escalation_rule_node,
    evidence_retriever_node,
    guideline_version_selector_node,
    human_review_gate_node,
    query_validation_node,
    secure_output_node,
    sensitive_content_minimization_node,
)
from src.schemas.state import State

_SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
TRUST = TrustLevel.VERIFIED_EXTERNAL.value

SAMPLE_PAYLOAD = json.dumps({"question": "Is my JSPS proposal eligible under the current call?", "grant_program": "jsps"})

# Privileged (outer-boundary) nodes — required_trust_level != ANONYMOUS.
PRIVILEGED_NODE_CLASSES = (
    query_validation_node.QueryValidationNode,
    secure_output_node.SecureOutputNode,
)

ALL_NODE_CLASSES = (
    query_validation_node.QueryValidationNode,
    sensitive_content_minimization_node.SensitiveContentMinimizationNode,
    guideline_version_selector_node.GuidelineVersionSelectorNode,
    evidence_retriever_node.EvidenceRetrieverNode,
    eligibility_answer_draft_node.EligibilityAnswerDraftNode,
    escalation_rule_node.EscalationRuleNode,
    human_review_gate_node.HumanReviewGateNode,
    secure_output_node.SecureOutputNode,
)


def _src_files():
    for root, _d, files in os.walk(_SRC):
        for f in files:
            if f.endswith(".py"):
                yield os.path.join(root, f)


# TC-01 - State is a flat TypedDict extending AgentState; added fields are
# JSON-serializable primitives (NotRequired-wrapped).
class TestTC01StateContract:
    def test_state_is_typeddict_extending_agent_state(self):
        assert hasattr(State, "__annotations__")
        assert "user_input" in State.__annotations__
        assert set(AgentState.__annotations__).issubset(set(State.__annotations__))

    def test_added_fields_are_json_safe(self):
        added = [k for k in State.__annotations__ if k not in AgentState.__annotations__]
        assert added, "State must declare agent-specific fields"
        for name in added:
            ann_str = str(State.__annotations__[name])
            assert any(t in ann_str for t in ("str", "int", "bool", "float", "list", "dict")), (
                f"{name}: {ann_str} - fields must be JSON-serializable primitives/containers"
            )


# TC-02 - Empty/missing/invalid input yields a fail-closed ERROR outcome, no raise.
class TestTC02Validation:
    def test_empty_input_no_raise(self):
        out = query_validation_node.QueryValidationNode().execute({"user_input": ""})
        assert out["status"] == AgentStatus.ERROR
        assert out["error_log"]

    def test_missing_fields_no_raise(self):
        out = query_validation_node.QueryValidationNode().execute(
            {"user_input": json.dumps({"grant_program": "jsps"})}
        )
        assert out["status"] == AgentStatus.ERROR
        assert out["error_log"]


# TC-03 - No JWT / API keys / secrets in src/; no direct os.environ reads.
class TestTC03NoCredentials:
    def test_no_credential_literals(self):
        pat = re.compile(r"(sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)")
        offenders = [fp for fp in _src_files() if pat.search(open(fp, encoding="utf-8").read())]
        assert offenders == []

    def test_no_os_environ_secret_reads(self):
        # src/api/server.py's INVOKE_AUTH_TOKEN read is the documented entry-point exception
        # (\"Entry-point exception\" — deployment-level caller credential, not an
        # agent secret; no InvocationContext exists yet at that point).
        allowed = {os.path.normpath(os.path.join(_SRC, "api", "server.py"))}
        offenders = [
            fp for fp in _src_files()
            if "os.environ" in open(fp, encoding="utf-8").read() and os.path.normpath(fp) not in allowed
        ]
        assert offenders == []


# TC-04 - InvocationContext is never stored in State after invoke.
class TestTC04ContextIsolation:
    def test_no_invocationcontext_in_state_after_invoke(self):
        from src.graph.graph import Graph

        agent = Graph()
        agent.compile()
        ctx = InvocationContext(session_id="tc04", caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="tester-tc04")
        result = agent.invoke(SAMPLE_PAYLOAD, ctx=ctx)
        for v in result.values():
            assert not isinstance(v, InvocationContext)

    def test_from_state_available(self):
        assert hasattr(InvocationContext, "from_state")


# TC-05 - Domain events: outer nodes emit >=1 domain event; no node under
# src/nodes/ ever re-emits a framework backbone lifecycle event.
class TestTC05Audit:
    def test_pre_process_emits_domain_event(self, monkeypatch):
        events = []
        monkeypatch.setattr(query_validation_node, "emit_trace_event", lambda e, p, s: events.append(e))
        out = query_validation_node.QueryValidationNode().execute({"user_input": SAMPLE_PAYLOAD})
        assert out["status"] == AgentStatus.SUCCESS
        assert "query_validation_started" in events
        assert not ({"node_start", "node_complete", "node_error", "node_skip"} & set(events))

    def test_source_has_no_backbone_events(self):
        pat = re.compile(r'emit_trace_event\(\s*["\'](node_start|node_complete|node_error|node_skip)["\']')
        offenders = [fp for fp in _src_files() if pat.search(open(fp, encoding="utf-8").read())]
        assert offenders == []


# TC-06 / TC-07 - S-2/S-3 gates are @final on FunctionNode (overriding raises TypeError at class def).
# NOTE: the local SDK mirror is a pre-`@final`-gate stub (no _security_gate_input/_security_gate_output
# on FunctionNode) — see docs/03_test_spec.md. These assertions run for real against the CI wheel
# (agenticstar-agentcore==1.0.0); locally they skip rather than false-fail.
_HAS_FINAL_GATES = hasattr(FunctionNode, "_security_gate_input")


@pytest.mark.skipif(not _HAS_FINAL_GATES, reason="local SDK mirror predates the @final S-2/S-3 gate — CI wheel is the gate of record")
class TestTC0607FinalGates:
    def test_input_gate_is_final(self):
        with pytest.raises(TypeError):

            class BadIn(FunctionNode):  # noqa: N801
                def _security_gate_input(self, state):
                    return state

    def test_output_gate_is_final(self):
        with pytest.raises(TypeError):

            class BadOut(FunctionNode):  # noqa: N801
                def _security_gate_output(self, result):
                    return result

    def test_extra_hook_is_overridable(self):
        assert (
            secure_output_node.SecureOutputNode._extra_security_gate_output
            is not FunctionNode._extra_security_gate_output
        )

    def test_output_gate_blocks_credentials(self):
        # The @final S-3 credential scan actually fires (not vacuous): a
        # credential in the result is blocked, never returned as-is.
        node = secure_output_node.SecureOutputNode()
        with pytest.raises(Exception):
            node._security_gate_output({"formatted_output": "token AKIAIOSFODNN7EXAMPLE leaked"})


# TC-08 - required_trust_level declared valid + enforced: insufficient trust -> ERROR,
# execute() must NOT run. Dedicated S-1 boundary coverage for every privileged node.
class TestTC08TrustGate:
    def test_declared_trust_levels_valid(self):
        for cls in ALL_NODE_CLASSES:
            assert cls.required_trust_level in (TrustLevel.ANONYMOUS, TrustLevel.VERIFIED_EXTERNAL, TrustLevel.INTERNAL)

    @pytest.mark.parametrize("node_cls", PRIVILEGED_NODE_CLASSES)
    def test_insufficient_trust_returns_error_before_execute(self, node_cls, monkeypatch):
        node = node_cls()
        executed = []
        monkeypatch.setattr(node_cls, "execute", lambda self, state, _e=executed: (_e.append(True), {})[1])
        out = node({"caller_trust_level": TrustLevel.ANONYMOUS.value, "user_input": SAMPLE_PAYLOAD})
        assert str(out.get("status")).lower().endswith("error")
        assert executed == [], "execute() must not run when caller trust is insufficient"

    @pytest.mark.parametrize("node_cls", PRIVILEGED_NODE_CLASSES)
    def test_sufficient_trust_succeeds(self, node_cls):
        node = node_cls()
        out = node({"caller_trust_level": TRUST, "user_input": SAMPLE_PAYLOAD})
        assert out["status"] == AgentStatus.SUCCESS
