"""AgentCore Platform v1.0 — grant-eligibility Q&A helpers (deterministic).

Service layer: pure deterministic domain helpers (the "Tool" layer the Agent
wraps). No routing, no credentials, no side effects. LLM reasoning and
orchestration stay in the nodes.
"""

from __future__ import annotations

from typing import Any
import re

ELIGIBLE = "eligible_indication"
INELIGIBLE = "ineligible_indication"
INSUFFICIENT = "insufficient_information"
VALID_INDICATIONS = (ELIGIBLE, INELIGIBLE, INSUFFICIENT)

DEFAULT_KB_VERSION = "v2026.1-admin-approved"
DEFAULT_CONFIDENCE_THRESHOLD = 0.6

DISCLAIMER = (
    "This is a non-binding administrative indication only. Final eligibility "
    "authority rests with the sponsor/university research-administration office."
)

# Deterministic patterns rejected at the input boundary (S-2): credential-shaped
# strings, Bearer tokens, or file-path traversal attempts have no legitimate
# place in an eligibility question.
_CREDENTIAL_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{10,}", re.IGNORECASE),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"\.\./"),
    re.compile(r"/etc/passwd"),
)

# Applicant/personnel PII + unpublished-research-detail markers — must be
# minimized/masked before retrieval (S-2). Curated per the design (Step 2).
_SENSITIVE_MARKERS = (
    "applicant_id",
    "applicant_name",
    "student_id",
    "personnel_id",
    "unpublished_manuscript",
    "unreleased_dataset",
)

VALID_GRANT_PROGRAMS = ("jsps", "amed", "jst", "institutional_seed_fund")


def contains_credential_pattern(text: str) -> bool:
    """Deterministic S-2 input scan — credential/Bearer/file-path shaped strings."""
    if not text:
        return False
    return any(p.search(text) for p in _CREDENTIAL_PATTERNS)


def is_valid_grant_program(program: str) -> bool:
    return (program or "").strip().lower() in VALID_GRANT_PROGRAMS


def minimize_sensitive_content(text: str) -> tuple[str, list[str]]:
    """Mask applicant-identifying / unpublished-research markers.

    Returns (masked_text, masked_field_names). Deterministic — no LLM.
    """
    masked_fields: list[str] = []
    result = text or ""
    low = result.lower()
    for marker in _SENSITIVE_MARKERS:
        if marker in low:
            masked_fields.append(marker)
            result = re.sub(re.escape(marker), "[REDACTED]", result, flags=re.IGNORECASE)
    return result, masked_fields


def select_guideline_version(grant_program: str) -> str:
    """Select the administrator-approved guideline version for the program.

    Deterministic lookup — a real deployment resolves this from an
    institution-curated version registry; the default here is the
    single administrator-approved version until per-program overrides exist.
    """
    return DEFAULT_KB_VERSION


def aggregate_retrieval_confidence(passages: list[dict[str, Any]]) -> float:
    """Deterministic confidence aggregate from retrieved passage scores."""
    if not passages:
        return 0.0
    scores = [float(p.get("score", 0.0)) for p in passages]
    return sum(scores) / len(scores) if scores else 0.0


def has_conflicting_passages(passages: list[dict[str, Any]]) -> bool:
    """Deterministic conflict check: passages tagged with opposing verdicts."""
    verdicts = {p.get("verdict") for p in passages if p.get("verdict")}
    return {"eligible", "ineligible"}.issubset(verdicts)


def decide_answer_indication(
    passages: list[dict[str, Any]],
    confidence: float,
    threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    llm_suggested: str | None = None,
) -> str:
    """Deterministic fail-safe rule — NEVER force eligible/ineligible on
    ambiguous or low-confidence retrieval. LLM drafting is explanatory only;
    this deterministic rule decides the final status.
    """
    if confidence < threshold:
        return INSUFFICIENT
    if not passages:
        return INSUFFICIENT
    if has_conflicting_passages(passages):
        return INSUFFICIENT
    if llm_suggested in VALID_INDICATIONS and llm_suggested != INSUFFICIENT:
        return llm_suggested
    directly_addressing = [p for p in passages if p.get("addresses_criteria")]
    if not directly_addressing:
        return INSUFFICIENT
    verdicts = {p.get("verdict") for p in directly_addressing if p.get("verdict")}
    if verdicts == {"eligible"}:
        return ELIGIBLE
    if verdicts == {"ineligible"}:
        return INELIGIBLE
    return INSUFFICIENT


def needs_escalation(
    answer_indication: str, passages: list[dict[str, Any]], confidence: float, threshold: float
) -> tuple[bool, str]:
    """Escalate exceptions, conflicts, or missing evidence to grant staff."""
    if answer_indication == INSUFFICIENT:
        return True, "insufficient_information — evidence incomplete or conflicting"
    if confidence < threshold:
        return True, "retrieval_confidence below configured threshold"
    if has_conflicting_passages(passages):
        return True, "conflicting guideline passages detected"
    return False, ""


def is_upstream_error(status: Any) -> bool:
    return str(status).lower().endswith("error")
