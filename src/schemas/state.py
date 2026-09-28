"""AgentCore Platform v1.0 — EDU-C2-076 state schema."""

# Flat TypedDict only (msgpack-safe). Extend AgentState with agent-specific
# fields; no credentials, secrets, or Pydantic models in State.

from typing import NotRequired

from framework.schemas.agent_state import AgentState


# Type-check note: the wheel ships no py.typed, so mypy resolves AgentState to Any
# and reports every NotRequired below as valid-type. The fields are correct (the state
# contract requires NotRequired) -- the report is a packaging artifact, suppressed per field.
# Drop these ignores once the wheel ships py.typed.
class State(AgentState):
    """University Research-Grant Eligibility Evidence Q&A Agent state.

    Shared fields (user_input, validated_input, status, node_history, result,
    formatted_output, ...) are inherited from AgentState. All agent-specific
    fields are NotRequired[...] and read via state.get(...).
    """

    grant_program: NotRequired[str]  # type: ignore[valid-type]
    protected_query: NotRequired[str]  # type: ignore[valid-type]
    kb_version: NotRequired[str]  # type: ignore[valid-type]
    retrieved_passages: NotRequired[list[dict]]  # type: ignore[valid-type]
    retrieval_confidence: NotRequired[float]  # type: ignore[valid-type]
    # eligible_indication | ineligible_indication | insufficient_information
    answer_indication: NotRequired[str]  # type: ignore[valid-type]
    cited_passages: NotRequired[list[dict]]  # type: ignore[valid-type]
    assumptions: NotRequired[list[str]]  # type: ignore[valid-type]
    escalation_condition: NotRequired[str]  # type: ignore[valid-type]
    escalation_flag: NotRequired[bool]  # type: ignore[valid-type]
    # auto_cleared | pending_staff_review | staff_confirmed
    review_status: NotRequired[str]  # type: ignore[valid-type]
    disclaimer: NotRequired[str]  # type: ignore[valid-type]
    answer_text: NotRequired[str]  # type: ignore[valid-type]
