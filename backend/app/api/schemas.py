"""
app/api/schemas.py

Pydantic models for API request and response validation.

Why separate schemas from SQLAlchemy models?
  - SQLAlchemy models represent database tables
  - Pydantic schemas represent what the API accepts/returns
  - They're often similar but serve different purposes:
    * DB models have relationships, lazy loading, ORM magic
    * API schemas are plain data — serializable to JSON
    * Keeping them separate means DB changes don't break the API contract

This file defines the "contract" of our API — what callers
must send and what they'll receive back.
"""
from pydantic import BaseModel, Field
from typing import Any
from datetime import datetime


# ── Request Schemas ───────────────────────────────────────────────────────────

class VerifyRequest(BaseModel):
    """
    Request body for POST /api/v1/verify

    Example:
        {
            "claim": "The Eiffel Tower is 330 meters tall",
            "max_iterations": 5
        }
    """
    claim: str = Field(
        ...,                    # ... means required
        min_length=10,
        max_length=1000,
        description="The claim to fact-check",
        examples=["The Eiffel Tower is 330 meters tall"],
    )
    max_iterations: int = Field(
        default=5,
        ge=1,                   # ge = greater than or equal to
        le=10,                  # le = less than or equal to
        description="Max agent loop iterations (1-10)",
    )


# ── Response Schemas ──────────────────────────────────────────────────────────

class EvidenceNodeSchema(BaseModel):
    """A single piece of evidence in the response graph."""
    id: str
    text: str
    kg_entity_id: str | None = None
    kg_property_id: str | None = None
    attributes: dict[str, Any] | None = None
    retrieved_at: datetime | None = None
    source_url: str | None = None
    source_type: str | None = None
    source_domain: str | None = None


class EvidenceEdgeSchema(BaseModel):
    """
    A relationship between the claim and a piece of evidence.
    This is what the frontend renders as colored graph edges.
    """
    id: str
    relation_type: str          # "supported_by", "contradicted_by", etc.
    relevance_score: float | None = None
    support_score: float | None = None
    reasoning: str | None = None
    evidence_node_id: str


class EvidenceGraphSchema(BaseModel):
    """
    The full evidence graph — nodes + edges.
    This is what the React frontend will visualize.
    """
    nodes: list[EvidenceNodeSchema]
    edges: list[EvidenceEdgeSchema]
    node_count: int
    supporting_count: int       # How many edges support the claim
    contradicting_count: int    # How many edges contradict it


class CitationSchema(BaseModel):
    """A source citation — shown in the UI as a reference list."""
    url: str
    title: str | None = None
    domain: str | None = None
    source_type: str
    reliability_score: float | None = None


class VerifyResponse(BaseModel):
    """
    Full response from POST /api/v1/verify

    This is the complete output of one ProofChain fact-check run.
    Every field maps to something visible in the UI (Phase 8).
    """
    # ── Core Verdict ──────────────────────────────────────
    claim: str
    verdict: str                # "supported", "contradicted", etc.
    confidence: float           # 0.0 - 1.0
    verdict_explanation: str | None = None

    # ── Evidence Graph ────────────────────────────────────
    evidence_graph: EvidenceGraphSchema

    # ── Citations ─────────────────────────────────────────
    citations: list[CitationSchema]

    # ── Transparency ──────────────────────────────────────
    failure_modes: list[str]    # Ways this verdict could be wrong
    iterations_used: int        # How many agent loops it took
    cached: bool = False        # Was this result served from cache?

    # ── Metadata ──────────────────────────────────────────
    processing_time_ms: float | None = None


class VerifyErrorResponse(BaseModel):
    """Returned when verification fails."""
    error: str
    detail: str | None = None