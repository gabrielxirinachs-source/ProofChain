"""

This is the core knowledge graph retrieval service.
It talks to Wikidata's public SPARQL endpoint to pull
structured facts about entities.

What is SPARQL?
  SPARQL is a query language for graph databases — think SQL but for
  graphs. Instead of tables/rows, you query nodes/edges.

  Example SPARQL query:
    SELECT ?height WHERE {
      wd:Q243 wdt:P2048 ?height .   # Q243=Eiffel Tower, P2048=height
    }

Wikidata's endpoint is completely free and requires no API key.
We just need to set a User-Agent header to be a good citizen.
"""
import httpx
from dataclasses import dataclass
from app.core.config import get_settings

settings = get_settings()

# Wikidata SPARQL endpoint — free, no auth required
SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"

# Wikidata entity search API
SEARCH_ENDPOINT = "https://www.wikidata.org/w/api.php"


@dataclass
class WikidataEntity:
    """
    Represents a Wikidata entity found by search.

    Example:
        WikidataEntity(
            entity_id="Q243",
            label="Eiffel Tower",
            description="lattice tower on the Champ de Mars in Paris",
        )
    """
    entity_id: str      # e.g. "Q243"
    label: str          # e.g. "Eiffel Tower"
    description: str    # e.g. "lattice tower on the Champ de Mars in Paris"


@dataclass
class WikidataFact:
    """
    Represents a single fact (triple) from Wikidata.

    A triple is: subject → property → value
    Example: Eiffel Tower → height → 330 metre

        WikidataFact(
            entity_id="Q243",
            entity_label="Eiffel Tower",
            property_id="P2048",
            property_label="height",
            value="330",
            value_unit="metre",
        )
    """
    entity_id: str
    entity_label: str
    property_id: str
    property_label: str
    value: str
    value_unit: str | None = None       # e.g. "metre", "kilogram"
    value_entity_id: str | None = None  # If value is another entity (e.g. Q90 for Paris)


async def search_entity(entity_name: str) -> WikidataEntity | None:
    """
    Search Wikidata for an entity by name.
    Returns the best match or None if not found.

    Args:
        entity_name: Human-readable name, e.g. "Eiffel Tower"

    Returns:
        WikidataEntity with ID, label, description — or None
    """
    params = {
        "action": "wbsearchentities",
        "search": entity_name,
        "language": "en",
        "format": "json",
        "limit": 1,         # We only want the best match
        "type": "item",
    }

    headers = {"User-Agent": settings.WIKIDATA_USER_AGENT}

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            SEARCH_ENDPOINT,
            params=params,
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()

    results = data.get("search", [])
    if not results:
        return None

    best = results[0]
    return WikidataEntity(
        entity_id=best["id"],
        label=best.get("label", entity_name),
        description=best.get("description", ""),
    )


async def get_entity_facts(entity_id: str) -> list[WikidataFact]:
    """
    Query Wikidata for key facts about an entity using SPARQL.

    We fetch a curated set of the most fact-checkable properties:
    dates, quantities, locations, relationships — things that can
    actually support or contradict a claim.

    Args:
        entity_id: Wikidata entity ID, e.g. "Q243"

    Returns:
        List of WikidataFact objects
    """
    # This SPARQL query fetches important properties for the entity.
    #
    # Breaking it down:
    #   wd:Q243          → the specific entity we're querying
    #   ?prop            → any property (we'll filter to important ones)
    #   ?propLabel       → human-readable property name
    #   ?value           → the value of that property
    #   SERVICE wikibase:label → auto-fetches human-readable labels
    #
    # We filter to the most fact-checkable property types using
    # a VALUES clause with common Wikidata property IDs.
    sparql_query = f"""
    SELECT ?prop ?propLabel ?value ?valueLabel ?unit ?unitLabel WHERE {{
      wd:{entity_id} ?prop ?value .

      # Only fetch properties that are fact-checkable
      VALUES ?prop {{
        wdt:P571   # inception / founding date
        wdt:P576   # dissolved date
        wdt:P569   # date of birth
        wdt:P570   # date of death
        wdt:P19    # place of birth
        wdt:P20    # place of death
        wdt:P27    # country of citizenship
        wdt:P17    # country
        wdt:P131   # located in administrative territory
        wdt:P625   # coordinate location (skip — complex type)
        wdt:P2048  # height
        wdt:P2049  # width
        wdt:P2046  # area
        wdt:P1082  # population
        wdt:P159   # headquarters location
        wdt:P112   # founded by
        wdt:P84    # architect
        wdt:P170   # creator
        wdt:P50    # author
        wdt:P57    # director
        wdt:P495   # country of origin
        wdt:P31    # instance of (what type of thing is this)
        wdt:P279   # subclass of
        wdt:P18    # image (skip — URL not useful for text)
      }}

      # Get human-readable labels for everything
      SERVICE wikibase:label {{
        bd:serviceParam wikibase:language "en" .
        ?prop rdfs:label ?propLabel .
        ?value rdfs:label ?valueLabel .
      }}

      # Optionally get units for numeric values (height in metres, etc.)
      OPTIONAL {{
        ?value wikibase:quantityUnit ?unit .
        SERVICE wikibase:label {{
          bd:serviceParam wikibase:language "en" .
          ?unit rdfs:label ?unitLabel .
        }}
      }}
    }}
    LIMIT 50
    """

    headers = {
        "User-Agent": settings.WIKIDATA_USER_AGENT,
        "Accept": "application/sparql-results+json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            SPARQL_ENDPOINT,
            params={"query": sparql_query, "format": "json"},
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()

    facts = []
    bindings = data.get("results", {}).get("bindings", [])

    for binding in bindings:
        # Extract property ID from the full URI
        # e.g. "http://www.wikidata.org/prop/direct/P2048" → "P2048"
        prop_uri = binding.get("prop", {}).get("value", "")
        prop_id = prop_uri.split("/")[-1] if prop_uri else ""

        prop_label = binding.get("propLabel", {}).get("value", prop_id)
        value_label = binding.get("valueLabel", {}).get("value", "")
        unit_label = binding.get("unitLabel", {}).get("value", None)

        # Skip coordinates and image URLs — not useful as text evidence
        if prop_id in ("P625", "P18"):
            continue

        # Skip if value is just a Wikidata URI (not human-readable)
        raw_value = binding.get("value", {}).get("value", "")
        if raw_value.startswith("http://www.wikidata.org") and not value_label:
            continue

        # Build human-readable value
        display_value = value_label or raw_value

        # Extract value entity ID if the value is a Wikidata entity
        value_entity_id = None
        if raw_value.startswith("http://www.wikidata.org/entity/Q"):
            value_entity_id = raw_value.split("/")[-1]

        facts.append(WikidataFact(
            entity_id=entity_id,
            entity_label="",        # Filled in by the caller
            property_id=prop_id,
            property_label=prop_label,
            value=display_value,
            value_unit=unit_label if unit_label != "1" else None,
            value_entity_id=value_entity_id,
        ))

    return facts


async def retrieve_evidence_for_entity(entity_name: str) -> tuple[WikidataEntity | None, list[WikidataFact]]:
    """
    Full pipeline: search for entity → get its facts.
    This is the main entry point used by the agent loop.

    Returns:
        (entity, facts) tuple — entity is None if not found
    """
    entity = await search_entity(entity_name)
    if not entity:
        return None, []

    facts = await get_entity_facts(entity.entity_id)

    # Fill in entity label on each fact
    for fact in facts:
        fact.entity_label = entity.label

    return entity, facts