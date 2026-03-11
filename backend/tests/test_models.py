"""

These tests verify our SQLAlchemy models are correctly structured.
We test the model logic (enums, defaults, repr) without needing
a live database — keeping tests fast and isolated.

Phase 2 will add integration tests that actually write to Postgres.
"""
import uuid
import pytest
from datetime import datetime, timezone

from app.models.claim import Claim, VerdictType
from app.models.source import Source, SourceType
from app.models.evidence_node import EvidenceNode
from app.models.evidence_edge import EvidenceEdge, EdgeRelationType


class TestVerdictType:
    def test_all_verdicts_defined(self):
        """Ensure no verdict value was accidentally removed."""
        verdicts = {v.value for v in VerdictType}
        assert "supported" in verdicts
        assert "contradicted" in verdicts
        assert "partially_supported" in verdicts
        assert "insufficient" in verdicts
        assert "unverifiable" in verdicts

    def test_verdict_is_string_enum(self):
        """VerdictType should be usable as a string directly."""
        assert VerdictType.SUPPORTED == "supported"


class TestEdgeRelationType:
    def test_relation_types_defined(self):
        relations = {r.value for r in EdgeRelationType}
        assert "supported_by" in relations
        assert "contradicted_by" in relations

    def test_relation_is_string_enum(self):
        assert EdgeRelationType.CONTRADICTED_BY == "contradicted_by"


class TestClaimModel:
    def test_claim_instantiation(self):
        """Claim should be creatable with just a text field."""
        claim = Claim(text="The Eiffel Tower is 330 meters tall.")
        assert claim.text == "The Eiffel Tower is 330 meters tall."
        assert claim.verdict is None       # Unverified by default
        assert claim.confidence is None

    def test_claim_repr(self):
        claim = Claim(text="Short claim text")
        assert "Claim" in repr(claim)
        assert "Short claim text" in repr(claim)


class TestSourceModel:
    def test_source_instantiation(self):
        source = Source(
            url="https://www.wikidata.org/wiki/Q243",
            source_type=SourceType.WIKIDATA,
            domain="wikidata.org",
        )
        assert source.source_type == SourceType.WIKIDATA
        assert source.domain == "wikidata.org"

    def test_source_repr(self):
        source = Source(
            url="https://wikidata.org/Q243",
            source_type=SourceType.WIKIDATA,
            domain="wikidata.org",
        )
        assert "wikidata" in repr(source)


class TestEvidenceNodeModel:
    def test_evidence_node_instantiation(self):
        source_id = uuid.uuid4()
        node = EvidenceNode(
            text="The Eiffel Tower stands 330 metres tall.",
            kg_entity_id="Q243",
            kg_property_id="P2048",
            attributes={"height": "330", "unit": "metre"},
            source_id=source_id,
        )
        assert node.kg_entity_id == "Q243"
        assert node.attributes["unit"] == "metre"
        assert node.embedding is None  # Not set until Phase 3

    def test_evidence_node_repr(self):
        node = EvidenceNode(
            text="Some evidence text here",
            kg_entity_id="Q243",
            source_id=uuid.uuid4(),
        )
        assert "Q243" in repr(node)


class TestEvidenceEdgeModel:
    def test_edge_instantiation(self):
        edge = EvidenceEdge(
            relation_type=EdgeRelationType.SUPPORTED_BY,
            relevance_score=0.92,
            support_score=0.88,
            reasoning="The source directly states the height matches the claim.",
            claim_id=uuid.uuid4(),
            evidence_node_id=uuid.uuid4(),
        )
        assert edge.relation_type == EdgeRelationType.SUPPORTED_BY
        assert edge.relevance_score == 0.92

    def test_edge_repr(self):
        edge = EvidenceEdge(
            relation_type=EdgeRelationType.CONTRADICTED_BY,
            claim_id=uuid.uuid4(),
            evidence_node_id=uuid.uuid4(),
        )
        assert "contradicted_by" in repr(edge)