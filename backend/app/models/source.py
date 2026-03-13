"""

A Source is WHERE a piece of evidence came from.
Separating sources from evidence nodes lets us:
  - Deduplicate: multiple evidence nodes can point to the same source
  - Track reliability: score sources over time
  - Show provenance: every fact traces back to a URL or KG entity
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Float, DateTime,  Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import enum

from app.db.session import Base


class SourceType(str, enum.Enum):
    """
    Where did this evidence come from?
    Keeping this typed helps the UI show different icons/badges per source type.
    """
    WIKIDATA = "wikidata"       # Structured KG — highest trust
    WIKIPEDIA = "wikipedia"     # Semi-structured — high trust
    NEWS = "news"               # Live web — medium trust
    WEB = "web"                 # Generic web page — lower trust
    ACADEMIC = "academic"       # Academic paper — high trust


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # ── Identity ──────────────────────────────────────────
    url: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
        unique=True,   # Deduplicate: same URL = same source row
        index=True,
    )
    source_type: Mapped[str] = mapped_column(
        SAEnum(SourceType, name="source_type"),
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    domain: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)

    # ── Trust / Reliability ───────────────────────────────
    # Future: update this score based on historical accuracy
    reliability_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="0.0 = unreliable, 1.0 = highly reliable",
    )

    # ── Provenance ────────────────────────────────────────
    fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When we last retrieved content from this source",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ── Relationships ─────────────────────────────────────
    evidence_nodes: Mapped[list["EvidenceNode"]] = relationship(  # noqa: F821
        "EvidenceNode",
        back_populates="source",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Source type={self.source_type} domain={self.domain} url={self.url[:60]!r}>"