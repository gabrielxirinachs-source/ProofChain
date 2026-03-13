"""

An EvidenceNode is a single, atomic piece of evidence.
Examples:
  - "Eiffel Tower was completed in 1889" (from Wikidata)
  - "The tower stands 330 metres tall" (from Wikipedia)
  - "Engineer Gustave Eiffel designed it" (from a news article)

The MOST IMPORTANT field here is `embedding`:
  - It's a 1536-dimensional vector (OpenAI text-embedding-3-small output)
  - Stored in Postgres via pgvector
  - Enables semantic search: find evidence SIMILAR IN MEANING to a claim
    even if the exact words don't match

Without vectors, we'd only find evidence with keyword matching.
With vectors, "tower height is 330m" matches "structure is 330 metres tall".
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from pgvector.sqlalchemy import Vector

from app.db.session import Base


class EvidenceNode(Base):
    __tablename__ = "evidence_nodes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # ── Content ───────────────────────────────────────────
    text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="The extracted text snippet that constitutes this piece of evidence",
    )

    # ── THE KEY FIELD: Vector Embedding ───────────────────
    # Vector(1536) matches OpenAI's text-embedding-3-small dimensions.
    # This column is what makes semantic similarity search possible.
    # Phase 3 will populate this when we retrieve evidence from Wikidata/web.
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(1536),
        nullable=True,
        comment="Semantic embedding of the evidence text — enables similarity search",
    )

    # ── Knowledge Graph Metadata ──────────────────────────
    # When evidence comes from Wikidata, we store the entity/property IDs
    # so we can expand the graph further (Phase 3)
    kg_entity_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="Wikidata entity ID, e.g. Q243 for Eiffel Tower",
    )
    kg_property_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="Wikidata property ID, e.g. P2048 for height",
    )

    # ── Structured Attributes ─────────────────────────────
    # JSONB lets us store arbitrary key-value pairs from KG triples.
    # e.g. {"height": "330m", "unit": "metre", "point_in_time": "1889"}
    # JSONB (vs JSON) is indexed and queryable in Postgres.
    attributes: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Structured attributes extracted from KG triples or web content",
    )

    # ── Provenance ────────────────────────────────────────
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        comment="When this evidence was retrieved — important for freshness scoring",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ── Foreign Keys ──────────────────────────────────────
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
    )

    # ── Relationships ─────────────────────────────────────
    source: Mapped["Source"] = relationship(  # noqa: F821
        "Source",
        back_populates="evidence_nodes",
        lazy="selectin",
    )
    evidence_edges: Mapped[list["EvidenceEdge"]] = relationship(  # noqa: F821
        "EvidenceEdge",
        back_populates="evidence_node",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<EvidenceNode id={self.id} kg={self.kg_entity_id} text={self.text[:50]!r}>"