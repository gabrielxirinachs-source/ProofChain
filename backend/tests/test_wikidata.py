"""

Tests for the Wikidata retrieval pipeline.

We split tests into two categories:
  1. Unit tests  — test logic without any network calls (fast, always run)
  2. Integration tests — make real Wikidata API calls (slower, require internet)

Integration tests are marked with @pytest.mark.integration so you can
skip them in CI with: pytest -m "not integration"
Run them locally with: pytest -m integration -v
"""
import pytest
from unittest.mock import AsyncMock, patch

from app.services.entity_extractor import _parse_entity_response
from app.services.wikidata_client import WikidataEntity, WikidataFact
from app.services.evidence_builder import (
    fact_to_text,
    deduplicate_facts,
    build_wikidata_source,
    build_evidence_nodes,
)
import uuid


# ── Unit Tests (no network needed) ───────────────────────────────────────────

class TestEntityResponseParser:
    """Tests for the LLM response parser — no API calls needed."""

    def test_parses_clean_json(self):
        raw = '["Eiffel Tower", "Paris"]'
        result = _parse_entity_response(raw)
        assert result == ["Eiffel Tower", "Paris"]

    def test_parses_json_with_markdown_fences(self):
        """LLMs sometimes wrap output in ```json blocks."""
        raw = '```json\n["Albert Einstein", "Ulm"]\n```'
        result = _parse_entity_response(raw)
        assert result == ["Albert Einstein", "Ulm"]

    def test_returns_empty_list_for_garbage(self):
        result = _parse_entity_response("I cannot extract entities from this.")
        assert result == []

    def test_filters_empty_strings(self):
        raw = '["Eiffel Tower", "", "Paris"]'
        result = _parse_entity_response(raw)
        assert "" not in result
        assert "Eiffel Tower" in result

    def test_handles_empty_array(self):
        result = _parse_entity_response("[]")
        assert result == []


class TestFactToText:
    """Tests for converting WikidataFacts to human-readable text."""

    def test_basic_fact(self):
        fact = WikidataFact(
            entity_id="Q243",
            entity_label="Eiffel Tower",
            property_id="P2048",
            property_label="height",
            value="330",
            value_unit="metre",
        )
        text = fact_to_text(fact)
        assert "Eiffel Tower" in text
        assert "height" in text
        assert "330" in text
        assert "metre" in text

    def test_fact_without_unit(self):
        fact = WikidataFact(
            entity_id="Q243",
            entity_label="Eiffel Tower",
            property_id="P571",
            property_label="inception",
            value="1889",
        )
        text = fact_to_text(fact)
        assert "Eiffel Tower" in text
        assert "inception" in text
        assert "1889" in text

    def test_no_duplicate_unit(self):
        """Unit should not appear twice if already in value string."""
        fact = WikidataFact(
            entity_id="Q243",
            entity_label="Eiffel Tower",
            property_id="P2048",
            property_label="height",
            value="330 metre",      # unit already in value
            value_unit="metre",
        )
        text = fact_to_text(fact)
        assert text.count("metre") == 1


class TestDeduplicateFacts:
    def test_removes_duplicates(self):
        facts = [
            WikidataFact("Q243", "Eiffel Tower", "P2048", "height", "330", "metre"),
            WikidataFact("Q243", "Eiffel Tower", "P2048", "height", "330", "metre"),
            WikidataFact("Q243", "Eiffel Tower", "P571", "inception", "1889"),
        ]
        result = deduplicate_facts(facts)
        assert len(result) == 2

    def test_keeps_different_facts(self):
        facts = [
            WikidataFact("Q243", "Eiffel Tower", "P2048", "height", "330", "metre"),
            WikidataFact("Q243", "Eiffel Tower", "P571", "inception", "1889"),
        ]
        result = deduplicate_facts(facts)
        assert len(result) == 2


class TestBuildWikidataSource:
    def test_source_has_correct_url(self):
        entity = WikidataEntity(
            entity_id="Q243",
            label="Eiffel Tower",
            description="lattice tower in Paris",
        )
        source = build_wikidata_source(entity)
        assert source.url == "https://www.wikidata.org/wiki/Q243"
        assert source.domain == "wikidata.org"
        assert source.reliability_score == 0.90

    def test_source_title_includes_label(self):
        entity = WikidataEntity("Q243", "Eiffel Tower", "")
        source = build_wikidata_source(entity)
        assert "Eiffel Tower" in source.title


class TestBuildEvidenceNodes:
    def test_builds_nodes_from_facts(self):
        facts = [
            WikidataFact("Q243", "Eiffel Tower", "P2048", "height", "330", "metre"),
            WikidataFact("Q243", "Eiffel Tower", "P571", "inception", "1889"),
        ]
        source_id = uuid.uuid4()
        nodes = build_evidence_nodes(facts, source_id)

        assert len(nodes) == 2
        assert all(n.source_id == source_id for n in nodes)
        assert all(n.embedding is None for n in nodes)  # Not set yet
        assert all(n.kg_entity_id == "Q243" for n in nodes)

    def test_nodes_have_attributes(self):
        facts = [
            WikidataFact("Q243", "Eiffel Tower", "P2048", "height", "330", "metre"),
        ]
        nodes = build_evidence_nodes(facts, uuid.uuid4())
        assert nodes[0].attributes["property_label"] == "height"
        assert nodes[0].attributes["value"] == "330"


# ── Integration Tests (require internet + Wikidata) ───────────────────────────

@pytest.mark.integration
async def test_search_eiffel_tower():
    """Real Wikidata search — requires internet."""
    from app.services.wikidata_client import search_entity
    entity = await search_entity("Eiffel Tower")

    assert entity is not None
    assert entity.entity_id == "Q243"
    assert "Eiffel" in entity.label


@pytest.mark.integration
async def test_get_eiffel_tower_facts():
    """Real Wikidata SPARQL query — requires internet."""
    from app.services.wikidata_client import get_entity_facts
    facts = await get_entity_facts("Q243")

    assert len(facts) > 0
    property_ids = [f.property_id for f in facts]
    # Eiffel Tower should have height and inception date
    assert "P2048" in property_ids or "P571" in property_ids


@pytest.mark.integration
async def test_full_retrieval_pipeline():
    """Full pipeline: entity name → facts → evidence nodes."""
    from app.services.wikidata_client import retrieve_evidence_for_entity
    from app.services.evidence_builder import build_wikidata_source, build_evidence_nodes, deduplicate_facts
    import uuid

    entity, facts = await retrieve_evidence_for_entity("Eiffel Tower")

    assert entity is not None
    assert len(facts) > 0

    facts = deduplicate_facts(facts)
    source = build_wikidata_source(entity)
    # Use a fake UUID since we're not hitting the DB
    nodes = build_evidence_nodes(facts, uuid.uuid4())

    assert len(nodes) > 0
    assert all(n.kg_entity_id == "Q243" for n in nodes)
    assert all(n.source_id is not None for n in nodes)