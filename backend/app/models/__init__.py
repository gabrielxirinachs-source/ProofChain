"""


Importing all models here serves two purposes:
  1. Clean imports elsewhere: `from app.models import Claim, EvidenceNode`
  2. Alembic discovery: when Alembic generates migrations, it needs to
     have seen all models before it can detect schema changes.
     Importing everything here + importing this module in alembic/env.py
     is the standard pattern.
"""
from app.models.claim import Claim, VerdictType
from app.models.source import Source, SourceType
from app.models.evidence_node import EvidenceNode
from app.models.evidence_edge import EvidenceEdge, EdgeRelationType

__all__ = [
    "Claim",
    "VerdictType",
    "Source",
    "SourceType",
    "EvidenceNode",
    "EvidenceEdge",
    "EdgeRelationType",
]