# EDU-C2-076 — University Research-Grant Eligibility Evidence Q&A Agent

> **Category**: Cat 2 (orchestrates multiple steps to accomplish a specific use case)
> **Industry**: EDU

## Overview

This agent answers research-grant eligibility questions for university research-administration
staff and researchers. It gives a cited, non-binding indication and never makes the final
eligibility decision. The caller sends JSON in the `input` string:
`{"question": "...", "grant_program": "jsps" | "amed" | "jst" | "institutional_seed_fund"}`.
Plain text is accepted too and is treated as the question, with no program selected.

The pipeline:

1. **Query validation** rejects empty or oversized input, credential- or file-path-shaped
   strings, and unknown grant programs.
2. **Sensitive-content minimization** masks applicant-identifying and unpublished-research
   markers before the question is used for retrieval.
3. **Guideline version selection** picks the administrator-approved guideline version for the
   program.
4. **Evidence retrieval** searches the guideline knowledge base through an injected `retriever`
   (`search(query, filters, top_k)`) and computes an aggregate retrieval confidence.
5. **Answer drafting** applies a deterministic fail-safe rule. The result is `eligible` or
   `ineligible` only when confidence meets the threshold, passages do not conflict and the
   passages that address the criteria agree. Everything else is `insufficient_information`.
   An optional LLM may suggest an indication, but only after those confidence and conflict
   checks have passed.
6. **Escalation and human-review gating** flag insufficient, low-confidence or conflicting
   cases as `pending_staff_review`.
7. **Secure output** renders the answer with a non-binding disclaimer.

**Current behaviour as shipped.** The standalone entry point does not wire a retriever, so
retrieval returns no passages. Every question then resolves to `insufficient_information` and
is escalated for staff review. To get real indications, inject a `retriever` over your own
curated guideline corpus (and, optionally, an LLM client) through the graph configuration.
Tunables such as `top_k` and `confidence_threshold` live in `config/config.yaml`.

This is an agent template built with the **AGENTIC STAR** development platform and the
**AgentCore Framework**. It is intended to be taken as a starting point: fork it, adapt it to
your own data and policies, and run it inside your own AGENTIC STAR deployment.

## Requirements

**This template does not run standalone.** It requires:

| Requirement | Notes |
|---|---|
| **AGENTIC STAR platform** | The agent connects to the platform at start-up. Without it, start-up fails immediately (see *Behaviour without the platform* below). Deployment guides and API documentation: [AGENTIC STAR Developers](https://developers.fd.agenticstar.tm.softbank.jp/) |
| **AgentCore Framework** (`agenticstar-agentcore`) | Installed from PyPI as a dependency. |
| Python | 3.11 or later |

```bash
pip install -e .
```

### Behaviour without the platform

The framework is designed to run **only** on AGENTIC STAR. There is no fallback or degraded
mode. If the platform is unreachable or the SDK version does not match, the agent raises
`PlatformRequired` during graph compile / start-up preflight rather than starting in a partially
working state. This is intentional — a half-running agent is worse than one that refuses to start.

## Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests/ -v
```

Tests run without a platform connection. Running the agent itself does not.

## Project Structure

```
src/          agent implementation (nodes, services, schemas)
tests/        unit, integration and boundary tests
config/       agent configuration
docs/         design and test specification
```

See `docs/02_design.md` for the design and `docs/03_test_spec.md` for the test specification.

## Customising

1. Adjust `config/` for your own environment and policies.
2. Replace the knowledge sources and sample data with your own.
3. Review the node implementations under `src/nodes/` for domain-specific logic.
4. Re-run the test suite.

## License

MIT — see [LICENSE](LICENSE).

## Status of this repository

This template is published **as is**, by its individual author, under the MIT license. It carries
**no warranty and no support commitment**, and no organisation stands behind its behaviour or
fitness for any purpose. Issues and pull requests may or may not receive a response; that is at
the sole discretion of the repository owner.
