# Template Design Specification

## Position in AgentCore Architecture

- **Agent Class**: `Graph` (`src/graph/graph.py`)
- **L1 Base**: AgentBaseGraph
- **Three-Layer Separation**:
  - State: flat TypedDict composition (no Pydantic — msgpack incompatible)
  - Node: L1 inheritance (Template Method: `execute(self, state: dict) -> dict` override only)
  - Graph: composition (`register_nodes()` for node substitution)

## Architecture Overview

Cat 2 pattern — outer `AgentBaseGraph` backbone + `GraphNode` in the `main` slot wrapping an
inner `BaseGraph` domain workflow (`src/graph/eligibility_workflow_graph.py`).

### Node Configuration

| Node | Responsibility | Input State | Output State | Inherits/Overrides |
|------|---------------|-------------|--------------|-------------------|
| initialize | Sets schema_version, session_id, trust_level | user_input | node_history seed | InitializeNode (default) |
| pre_process | `QueryValidationNode` — S-1 + S-2 deterministic scan, grant_program validation | user_input | validated_input, grant_program | FunctionNode |
| main | `EligibilityGraphNode` — dispatches inner eligibility workflow | validated_input | protected_query, kb_version, retrieved_passages, retrieval_confidence, answer_indication, cited_passages, assumptions, escalation_flag, escalation_condition, review_status | GraphNode wrapping inner BaseGraph |
| ↳ inner: sensitive_content_minimization | Mask applicant/personnel PII + unpublished-research markers | user_input (JSON) | protected_query | FunctionNode (ANONYMOUS) |
| ↳ inner: guideline_version_selector | Select administrator-approved guideline version | grant_program | kb_version | FunctionNode (ANONYMOUS) |
| ↳ inner: evidence_retriever | Dense retrieval with kb_version filter, top_k @ config | protected_query, kb_version | retrieved_passages, retrieval_confidence | FunctionNode (ANONYMOUS) |
| ↳ inner: eligibility_answer_draft | Deterministic fail-safe answer indication (LLM explanatory only) | retrieved_passages, retrieval_confidence | answer_indication, cited_passages, assumptions | FunctionNode (ANONYMOUS) |
| ↳ inner: escalation_rule | Escalate exceptions/conflicts/missing evidence | answer_indication, retrieved_passages, retrieval_confidence | escalation_flag, escalation_condition | FunctionNode (ANONYMOUS) |
| ↳ inner: human_review_gate | Never decides; marks review_status for flagged cases | escalation_flag | review_status | FunctionNode (ANONYMOUS) |
| post_process | `SecureOutputNode` — S-3 structured-evidence-claim gate, disclaimer | answer_indication, cited_passages, escalation_flag | answer_text, disclaimer, formatted_output | FunctionNode |
| finalize | Builds response_metadata, total_time_ms | — | — | FinalizeNode (default) |

### Data Flow

```
START → initialize → pre_process(QueryValidationNode) → main(EligibilityGraphNode)
  → {inner: sensitive_content_minimization → guideline_version_selector → evidence_retriever
      → eligibility_answer_draft → escalation_rule → human_review_gate}
  → post_process(SecureOutputNode) → finalize → END
```

### State Definition

| Field | Type | Purpose | Required |
|-------|------|---------|----------|
| grant_program | `NotRequired[str]` | Selected grant program id (jsps/amed/jst/institutional_seed_fund) | No |
| protected_query | `NotRequired[str]` | Question after sensitive-content minimization | No |
| kb_version | `NotRequired[str]` | Administrator-approved guideline version selected | No |
| retrieved_passages | `NotRequired[list[dict]]` | Cited evidence passages from retrieval | No |
| retrieval_confidence | `NotRequired[float]` | Aggregate retrieval confidence score | No |
| answer_indication | `NotRequired[str]` | eligible_indication / ineligible_indication / insufficient_information | No |
| cited_passages | `NotRequired[list[dict]]` | Structured evidence claims (result-ID, source passage, source span) | No |
| assumptions | `NotRequired[list[str]]` | Assumptions noted when indication is not resolved | No |
| escalation_condition | `NotRequired[str]` | Reason for escalation, when flagged | No |
| escalation_flag | `NotRequired[bool]` | Whether the case is escalated to staff | No |
| review_status | `NotRequired[str]` | auto_cleared / pending_staff_review | No |
| disclaimer | `NotRequired[str]` | Non-binding disclaimer text | No |
| answer_text | `NotRequired[str]` | Final rendered answer text | No |

**State Constraints (mandatory):**
- Flat TypedDict only (primitives + JSON-serializable types)
- No JWT, API keys, credentials in State (checkpoint DB leakage)
- InvocationContext via `config["configurable"]` only (not in State)
- No Pydantic models, dataclass, arbitrary Python objects (msgpack incompatible)

## Framework Utilization

### Shared Components Used
- [x] InvocationContext (correlation_id, session_id, permissions, credential handle)
- [ ] ConnectionPolicy (retry/timeout strategy)
- [x] SecurityViolationError (path not raised in normal flow — deterministic ERROR status used instead)
- [x] S-2: `_extra_security_gate_input()` — not implemented; the deterministic credential-pattern
      scan and grant-program validation run directly in `QueryValidationNode.execute()` (fail-closed
      ERROR status, not raise) — the default framework PII scan on `user_input`/`validated_input`
      is sufficient for this template's domain checks
- [x] S-3: `_extra_security_gate_output()` — `SecureOutputNode` implements the structured
      evidence-claim gate: FAILs the whole package when a resolved answer_indication carries no
      citation, a citation references a passage not in the retrieved set, or an
      insufficient_information case is rendered as a resolved answer
- [x] S-4: `emit_trace_event()` — at least one domain-specific event inside each `execute()`
      (query_validation_started, sensitive_content_minimized, guideline_version_selected,
      evidence_retrieved, eligibility_answer_drafted, escalation_evaluated, human_review_gated,
      output_gated, plus GraphNode dispatch/completion events)

> **S-2/S-3 gate behaviour by node type (ADR-017):**
> - `FunctionNode` subclass → framework `@final` gate always runs automatically;
>   extend via `_extra_security_gate_input()` / `_extra_security_gate_output()` only
> - `GraphNode` / `RemoteAgentNode` → deliberate no-op (upstream or remote node's gate already applied)
> - Custom `BaseNode` subclass → must implement `_security_gate_input()` and
>   `_security_gate_output()` directly (`@abstractmethod` — omission raises `TypeError` at instantiation)

### Composition Pattern

- **Pattern**: GraphNode (subgraph) — Cat 2, outer `AgentBaseGraph` + `EligibilityGraphNode` in
  `main` slot wrapping inner `BaseGraph` (`EligibilityWorkflowGraph`)
- **Composition target**: `src/graph/eligibility_workflow_graph.py`
- **Error propagation strategy**: propagate (`error_strategy = "propagate"` — fail fast; no HITL
  interrupt inside the inner subgraph, `propagate_hitl = False`)

## Import Isolation Confirmation
- [x] Template does not import agenticstar-platform SDK (Level 0)
- [x] Import targets: framework/ and shared/ only (no agents/base/ required)

## Design Decision Record

| Decision | Option A | Option B | Chosen | Rationale |
|----------|----------|----------|--------|-----------|
| L1 base type | AgentBaseGraph | AutonomousBaseGraph | AgentBaseGraph | Fixed multi-step pipeline, no autonomous loop needed |
| Composition pattern | Flat 3-slot (Cat 1 style) | GraphNode + inner subgraph | GraphNode + inner subgraph | Cat 2 requires outer/inner split (`gate-composition`) |
| Human review mechanism | D6 `interrupt()` HITL pause | Synchronous review_status label | Synchronous review_status label | This is a synchronous Q&A endpoint, not a paused workflow; escalated cases are labeled `pending_staff_review` in the response rather than pausing graph execution. `hitl.enabled` stays `false`; PB-7 auto-skips. |
| Answer authority | LLM-decided indication | Deterministic confidence-threshold rule (LLM explanatory only) | Deterministic rule | The design mandates the fail-safe default (low confidence / conflicting passages / no direct-addressing passage → always `insufficient_information`), never LLM-forced |
