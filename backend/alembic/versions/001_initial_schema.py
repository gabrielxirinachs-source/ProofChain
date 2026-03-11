"""Initial schema: claims, sources, evidence_nodes, evidence_edges

Revision ID: 001_initial_schema
Revises: 
Create Date: 2025-01-01 00:00:00.000000

This is the first migration — it creates the entire initial schema.
Every future schema change (add a column, create an index, etc.)
will be a new migration file that builds on top of this one.

Run with: alembic upgrade head
Rollback with: alembic downgrade -1
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# Alembic uses these to track migration history in the DB
revision = '001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enable pgvector ───────────────────────────────────
    # Must run before creating any vector columns
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # ── sources ───────────────────────────────────────────
    op.create_table(
        'sources',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('url', sa.String(2048), nullable=False, unique=True),
        sa.Column('source_type', sa.String(32), nullable=False),
        sa.Column('title', sa.String(512), nullable=True),
        sa.Column('domain', sa.String(256), nullable=True),
        sa.Column('reliability_score', sa.Float(), nullable=True),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_sources_url', 'sources', ['url'])
    op.create_index('ix_sources_domain', 'sources', ['domain'])

    # ── claims ────────────────────────────────────────────
    op.create_table(
        'claims',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('verdict', sa.String(32), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('failure_modes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_claims_text', 'claims', ['text'])

    # ── evidence_nodes ────────────────────────────────────
    op.create_table(
        'evidence_nodes',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('text', sa.Text(), nullable=False),
        # Vector column — this is the pgvector magic
        # 1536 dims = OpenAI text-embedding-3-small
        sa.Column('embedding', Vector(1536), nullable=True),
        sa.Column('kg_entity_id', sa.String(64), nullable=True),
        sa.Column('kg_property_id', sa.String(64), nullable=True),
        sa.Column('attributes', postgresql.JSONB(), nullable=True),
        sa.Column('retrieved_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('source_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('sources.id', ondelete='CASCADE'), nullable=False),
    )
    op.create_index('ix_evidence_nodes_kg_entity', 'evidence_nodes', ['kg_entity_id'])

    # Vector similarity index — enables fast approximate nearest-neighbor search
    # cosine distance is best for normalized text embeddings
    op.execute("""
        CREATE INDEX ix_evidence_nodes_embedding
        ON evidence_nodes
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
    """)

    # ── evidence_edges ────────────────────────────────────
    op.create_table(
        'evidence_edges',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('relation_type', sa.String(32), nullable=False),
        sa.Column('relevance_score', sa.Float(), nullable=True),
        sa.Column('support_score', sa.Float(), nullable=True),
        sa.Column('reasoning', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('claim_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('claims.id', ondelete='CASCADE'), nullable=False),
        sa.Column('evidence_node_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('evidence_nodes.id', ondelete='CASCADE'), nullable=False),
    )
    op.create_index('ix_evidence_edges_claim_id', 'evidence_edges', ['claim_id'])
    op.create_index('ix_evidence_edges_relation', 'evidence_edges', ['relation_type'])


def downgrade() -> None:
    """Rollback: drop all tables in reverse dependency order."""
    op.drop_table('evidence_edges')
    op.drop_table('evidence_nodes')
    op.drop_table('claims')
    op.drop_table('sources')