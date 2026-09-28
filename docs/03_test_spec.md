# Test Specification

## Test Strategy
- Coverage target: all business-logic paths (unit + integration); hard % threshold enforced by CI gate
- Test types: Unit / Integration / Proof-of-Boundary

## Framework Compliance Tests (Mandatory)

| TC-ID | Test | Expected Result | Result |
|-------|------|----------------|--------|
| TC-01 | State contract: flat TypedDict | Type check pass, no Pydantic/dataclass | PASS |
| TC-02 | SecurityViolationError fires on invalid input | Error raised (fail-closed ERROR status) | PASS |
| TC-03 | No JWT/Credential in State | CI `gate-credential-scan`: 0 violations | PASS |
| TC-04 | InvocationContext via configurable only | Direct access raises error | PASS |
| TC-05 | S-4: no duplicate lifecycle events in `execute()` | `node_start` / `node_complete` / `node_error` absent from `execute()` body | 0 duplicates |
| TC-06 | S-2: `_security_gate_input()` not overridden (`FunctionNode` subclass) | `TypeError` raised at class definition if overridden (`@final` enforced by framework) | 0 overrides — CI gate of record (local wheel mirror lacks the `@final` gate; see note below) |
| TC-07 | S-3: `_security_gate_output()` not overridden (`FunctionNode` subclass) | `TypeError` raised at class definition if overridden (`@final` enforced by framework) | 0 overrides — CI gate of record |
| TC-08 | `required_trust_level` enforced | Insufficient trust → refused, `execute()` not called | PASS (parametrized over `QueryValidationNode`, `SecureOutputNode`) |
| TC-09 | S-2: `_extra_security_gate_input()` non-trivial when domain checks needed | Domain-specific input checks execute correctly | N/A — deterministic checks run in `execute()` directly (see docs/02_design.md); default framework scan sufficient |
| TC-10 | S-3: `_extra_security_gate_output()` non-trivial when domain checks needed | Domain-specific output checks execute correctly | PASS — `SecureOutputNode._extra_security_gate_output()` enforces the structured evidence-claim gate |
| TC-11 | S-4: at least one domain `emit_trace_event()` inside each `execute()` | Domain event emitted on every invocation path | PASS — every node in `src/nodes/` emits ≥1 domain event |

**Local test environment note:** an older local SDK build
is a pre-`@final`-gate stub of `agenticstar-agentcore` (no `_security_gate_input`/`_security_gate_output`
methods on `FunctionNode`). TC-06/TC-07's class-definition assertions and any test path that reaches the
real `_security_gate_output()` therefore cannot execute against the local mirror; this is an expected
local-environment adaptation, not a test failure. The CI pipeline installs the real
`agenticstar-agentcore==1.0.0` wheel and is the gate of record for TC-06/TC-07/PB-6.

## Proof-of-Boundary Tests (Mandatory)

| PB-ID | Boundary | Test | Expected Result | Result |
|-------|----------|------|----------------|--------|
| PB-1 | BaseNode → EventEmitter | `emit_trace_event()` fires on every invocation path | No silent failures | PASS |
| PB-2 | State serialization | Post-invoke State is primitives only | No Pydantic/dataclass | PASS |
| PB-3 | Level 2 → External service | Real external service connection (vector store retriever) | Data retrieved via injected `retriever.search()` | PASS (fake retriever in tests; real retriever wired via config at deploy) |
| PB-4 | Import isolation | No Level 0 imports | AST scan: 0 violations | PASS |
| PB-5 | Checkpoint safety | No JWT/Pydantic in checkpoint | Inspection pass | PASS |
| PB-6 | Invoke execution order | `__call__()`: S-1 trust gate → S-4 `node_start` → S-2 `_security_gate_input` → `execute()` → S-3 `_security_gate_output` → S-4 `node_complete` | Order verified | CI gate of record (local mirror lacks `emit_trace_event` hook in `base_node`) |
| PB-7 | HITL interrupt propagation *(conditional)* | Required only when `config/agent.yaml` sets `hitl.enabled: true`; otherwise record **Auto-waived — non-HITL** | `GraphInterrupt` propagates to the LangGraph engine; `status` is not set to `error` | Auto-waived — non-HITL (synchronous review_status label, not a paused HITL flow — see docs/02_design.md) |

> **Pre-review gate checklist:** PB-1 through PB-6 are mandatory. Evaluate PB-7 only for HITL-enabled templates. When neither HITL setting is true, mark PB-7 **Auto-waived — non-HITL**; its test is not required and must not block the gate.

## Business Logic Tests

| TC-ID | Test | Input | Expected Result | Result |
|-------|------|-------|----------------|--------|
| BL-01 | Eligible indication with citation | Question + grant_program with a retriever returning a high-confidence, criteria-addressing passage | `answer_indication=eligible_indication`, `cited_passages` non-empty, `disclaimer` present | PASS |
| BL-02 | Insufficient information — no evidence | Question with no retriever configured / empty retrieval | `answer_indication=insufficient_information`, `escalation_flag=true`, `review_status=pending_staff_review` | PASS |
| BL-03 | Credential/Bearer/file-path pattern rejected | Question containing a `Bearer sk-...` token | Fail-closed ERROR, no downstream processing | PASS |
| BL-04 | Sensitive-content minimization | Question containing an `applicant_id` marker | Marker masked as `[REDACTED]` before retrieval | PASS |
| BL-05 | Output gate blocks unsupported claim | `answer_indication=eligible_indication` with no `cited_passages` | S-3 gate FAILs the whole package | PASS |
| BL-06 | Output gate blocks insufficient rendered as resolved | `insufficient_information` with answer_text starting "Eligible indication..." | S-3 gate FAILs the whole package | PASS |

## Test Execution Summary
- Execution date: 2026-07-18
- Total tests: unit (test_nodes.py + test_framework_compliance.py) + integration (test_graph.py) + proof_of_boundary (4 files)
- Pass: business-logic + static (import isolation, state safety) tests pass locally. TC-06/TC-07/PB-6
  cannot execute against the local pre-`@final` SDK mirror (expected local adaptation, not a failure —
  see note above); these are the CI gate of record, verified green in the CI-green loop before merge.
- Coverage: all business-logic paths (unit + integration) exercised; hard % threshold enforced by CI gate
