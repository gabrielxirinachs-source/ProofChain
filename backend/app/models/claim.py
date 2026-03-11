"""

The Claim is the entry point for everything in ProofChain.
A user submits a claim, and the agent loop builds an evidence
graph around it to produce a verdict.

Design decisions:
  - UUIDs as primary keys: safer than sequential integers
    (no enumeration attacks, globally unique across services)
  - created_at / updated_at on every table: essential for
    provenance — you need to know WHEN a verdict was made
  - verdict is nullable: NULL means "not yet verified"
  - confidence is a float 0.0–1.0 (set by the agent loop)
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Float, DateTime, Text, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import enum

from app.db.session import Base


class VerdictType(str, enum.Enum):
    """
    The possible outcomes of fact-checking a claim.
    Using an Enum (not raw strings) means invalid verdicts
    are rejected at the Python level before touching the DB.
    """
    SUPPORTED = "supported"           # Evidence clearly supports the claim
    CONTRADICTED = "contradicted"     # Evidence clearly contradicts it
    PARTIALLY_SUPPORTED = "partially_supported"  # Mixed evidence
    INSUFFICIENT = "insufficient"     # Not enough evidence found
    UNVERIFIABLE = "unverifiable"     # Claim can't be checked (opinion, future, etc.)


class Claim(Base):
    __tablename__ = "claims"

    # ── Identity ──────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False, index=True)

    # ── Verdict (filled in by the agent loop) ─────────────
    verdict: Mapped[str | None] = mapped_column(
        SAEnum(VerdictType, name="verdict_type"),
        nullable=True,
    )
    confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="0.0 = no confidence, 1.0 = fully confident",
    )
    failure_modes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="JSON array of strings describing why verification might be wrong",
    )

    # ── Provenance ────────────────────────────────────────
    # timezone.utc ensures timestamps are always stored in UTC,
    # never ambiguous local time
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ── Relationships ─────────────────────────────────────
    # "lazy='selectin'" means SQLAlchemy automatically loads related
    # evidence nodes when you load a claim — no extra query needed.
    evidence_edges: Mapped[list["EvidenceEdge"]] = relationship(  # noqa: F821
        "EvidenceEdge",
        back_populates="claim",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Claim id={self.id} verdict={self.verdict} text={self.text[:50]!r}>"