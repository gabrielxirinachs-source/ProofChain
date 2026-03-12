"""


This service converts raw Wikidata facts into our internal
EvidenceNode + Source data structures.

It's the "translation layer" between the external world (Wikidata)
and our internal evidence graph schema.

Why a separate service for this?
  - Separation of concerns: wikidata_client.py fetches, this file transforms
  - Easy to add more sources later (web retrieval, academic papers)
    by writing a different builder that outputs the same types
  - Testable in isolation without needing live Wikidata calls
"""
from datetime import datetime, timezone
from app.models.evidence_node import EvidenceNode
from app.models.source import Source, SourceType
from app.services.wikidata_client import WikidataEntity, WikidataFact


def build_wikidata_source(entity: WikidataEntity) -> Source:
    """
    Create a Source record for a Wikidata entity.

    Each entity gets its own source pointing to its Wikidata page.
    This gives us full provenance — we can always trace an evidence
    node back to its exact Wikidata URL.

    Args:
        entity: WikidataEntity with id, label, description

    Returns:
        Source object (not yet saved to DB)
    """
    wikidata_url = f"https://www.wikidata.org/wiki/{entity.entity_id}"

    return Source(
        url=wikidata_url,
        source_type=SourceType.WIKIDATA,
        title=f"Wikidata: {entity.label}",
        domain="wikidata.org",
        reliability_score=0.90,     # Wikidata is high-trust structured data
        fetched_at=datetime.now(timezone.utc),
    )


def fact_to_text(fact: WikidataFact) -> str:
    """
    Convert a structured Wikidata fact into a human-readable sentence.

    This text is what gets stored in EvidenceNode.text and later
    embedded into a vector for semantic search.

    Examples:
        "Eiffel Tower height: 330 metre"
        "Albert Einstein date of birth: 14 March 1879"
        "Apple Inc founded by: Steve Jobs"

    Args:
        fact: WikidataFact with entity, property, value info

    Returns:
        Human-readable string representation
    """
    base = f"{fact.entity_label} {fact.property_label}: {fact.value}"

    # Append unit if present (e.g. "330 metre" instead of just "330")
    if fact.value_unit:
        # Check if unit is already in the value string to avoid duplication
        if fact.value_unit.lower() not in fact.value.lower():
            base = f"{fact.entity_label} {fact.property_label}: {fact.value} {fact.value_unit}"

    return base


def build_evidence_nodes(
    facts: list[WikidataFact],
    source_id,      # UUID of the already-saved Source
) -> list[EvidenceNode]:
    """
    Convert a list of WikidataFacts into EvidenceNode objects.

    Note: embeddings are NOT set here — that happens in Phase 5
    when the agent loop calls the embedding service. Setting them
    here would require an OpenAI API call per fact, which is expensive
    to do upfront before we know which facts are relevant.

    Args:
        facts: List of WikidataFact objects
        source_id: UUID of the Source record these nodes belong to

    Returns:
        List of EvidenceNode objects (not yet saved to DB)
    """
    nodes = []

    for fact in facts:
        text = fact_to_text(fact)

        # Skip facts that produced empty or meaningless text
        if not text.strip() or len(text) < 10:
            continue

        node = EvidenceNode(
            text=text,
            embedding=None,         # Set later during agent loop
            kg_entity_id=fact.entity_id,
            kg_property_id=fact.property_id,
            attributes={
                "entity_label": fact.entity_label,
                "property_label": fact.property_label,
                "value": fact.value,
                "value_unit": fact.value_unit,
                "value_entity_id": fact.value_entity_id,
            },
            source_id=source_id,
            retrieved_at=datetime.now(timezone.utc),
        )
        nodes.append(node)

    return nodes


def deduplicate_facts(facts: list[WikidataFact]) -> list[WikidataFact]:
    """
    Remove duplicate facts — same property with same value.

    Wikidata sometimes returns the same fact multiple times with
    slightly different formatting. We deduplicate before building
    evidence nodes to keep the graph clean.

    Args:
        facts: Raw list of facts from Wikidata

    Returns:
        Deduplicated list
    """
    seen = set()
    unique = []

    for fact in facts:
        # Use (property_id, value) as the deduplication key
        key = (fact.property_id, fact.value.lower().strip())
        if key not in seen:
            seen.add(key)
            unique.append(fact)

    return unique