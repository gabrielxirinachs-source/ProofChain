"""

The EvidenceEdge is what makes this a GRAPH, not just a flat list.

It's the relationship between a Claim and an EvidenceNode,
and it carries the most important semantic information:
  - Does this evidence SUPPORT or CONTRADICT the claim?
  - How relevant is it? (relevance_score)
  - What reasoning led the agent to connect them? (reasoning)

Think of it like this:
  Claim ──[edge: SUPPORTED_BY, score=0.92]──► EvidenceNode
  Claim ──[edge: CONTRADICTED_BY, score=0.78]──► EvidenceNode

The UI will render supporting edges in green, contradicting in red.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Float, DateTime, Text, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import enum

from app.db.session import Base


class EdgeRelationType(str, enum.Enum):
    """
    The semantic relationship between a claim and a piece of evidence.
    This is the core output of the agent's reasoning step.
    """
    SUPPORTED_BY = "supported_by"           # Evidence backs the claim
    CONTRADICTED_BY = "contradicted_by"     # Evidence refutes the claim
    PARTIALLY_SUPPORTS = "partially_supports"  # Evidence supports part of it
    CONTEXT = "context"                     # Related but neither supports nor contradicts
    IRRELEVANT = "irrelevant"               # Agent fetched it but it's not useful


class EvidenceEdge(Base):
    __tablename__ = "evidence_edges"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # ── The Graph Relationship ────────────────────────────
    relation_type: Mapped[str] = mapped_column(
        SAEnum(EdgeRelationType, name="edge_relation_type"),
        nullable=False,
        index=True,
    )

    # ── Scoring ───────────────────────────────────────────
    relevance_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="How relevant is this evidence to the claim? 0.0–1.0",
    )
    support_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Strength of support/contradiction. Positive=supports, Negative=contradicts",
    )

    # ── Agent Reasoning ───────────────────────────────────
    # This is the "show your work" field — the agent explains WHY
    # it connected this evidence to the claim with this relation type.
    # Critical for debuggability and the "evidence diff" feature.
    reasoning: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Agent's explanation for why this edge relation was assigned",
    )

    # ── Provenance ────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ── Foreign Keys ──────────────────────────────────────
    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evidence_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidence_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Relationships ─────────────────────────────────────
    claim: Mapped["Claim"] = relationship(  # noqa: F821
        "Claim",
        back_populates="evidence_edges",
    )
    evidence_node: Mapped["EvidenceNode"] = relationship(  # noqa: F821
        "EvidenceNode",
        back_populates="evidence_edges",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        relation = self.relation_type.value if hasattr(self.relation_type, 'value') else self.relation_type
        return (
            f"<EvidenceEdge {relation} "
            f"claim={self.claim_id} → node={self.evidence_node_id} "
            f"score={self.relevance_score}>"
        )