"""

This service takes a raw claim text and extracts the key entities
that we should look up in Wikidata.

Example:
  Input:  "The Eiffel Tower is 330 meters tall and was built in 1889"
  Output: ["Eiffel Tower"]

Why use an LLM for this instead of simple keyword extraction?
  - "The tower stands 330m" → LLM knows "tower" refers to Eiffel Tower in context
  - Handles abbreviations, alternate names, pronouns
  - Returns clean, searchable names rather than raw tokens

We use a small, cheap model (gpt-4o-mini) for this since it's a simple
classification task — no need for the expensive model here.
"""
import json
import re
from openai import AsyncOpenAI
from app.core.config import get_settings

settings = get_settings()


ENTITY_EXTRACTION_PROMPT = """You are an entity extraction system for a fact-checking engine.

Given a claim, extract the key named entities that should be looked up in a knowledge graph (Wikidata) to verify the claim.

Rules:
- Return ONLY a JSON array of strings, nothing else
- Include: people, places, organizations, events, landmarks, scientific concepts
- Exclude: generic nouns, numbers, dates, adjectives
- Return the most searchable form of each entity (e.g. "Eiffel Tower" not "the tower")
- Maximum 5 entities
- If no clear named entities exist, return an empty array []

Examples:
Claim: "The Eiffel Tower is 330 meters tall"
Output: ["Eiffel Tower"]

Claim: "Albert Einstein was born in Ulm, Germany in 1879"
Output: ["Albert Einstein", "Ulm"]

Claim: "Apple Inc was founded by Steve Jobs and Steve Wozniak"
Output: ["Apple Inc", "Steve Jobs", "Steve Wozniak"]

Now extract entities from this claim:
"""


async def extract_entities(claim_text: str) -> list[str]:
    """
    Extract named entities from a claim that can be looked up in Wikidata.

    Args:
        claim_text: The raw claim to fact-check

    Returns:
        List of entity name strings, e.g. ["Eiffel Tower", "Paris"]

    Example:
        entities = await extract_entities("The Eiffel Tower is 330 meters tall")
        # Returns: ["Eiffel Tower"]
    """
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {
                "role": "user",
                "content": f"{ENTITY_EXTRACTION_PROMPT}\nClaim: {claim_text}"
            }
        ],
        temperature=0,
        max_tokens=200,
    )

    raw = response.choices[0].message.content.strip()
    return _parse_entity_response(raw)


def _parse_entity_response(raw: str) -> list[str]:
    """
    Safely parse the LLM's JSON response.

    Why not just json.loads(raw)?
    Sometimes LLMs add markdown like ```json ... ``` around their output
    even when instructed not to. This function handles that gracefully.
    """
    try:
        result = json.loads(raw)
        if isinstance(result, list):
            return [str(e).strip() for e in result if e and str(e).strip()]
    except json.JSONDecodeError:
        pass

    # Fallback: extract JSON array from within the response
    match = re.search(r'\[.*?\]', raw, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, list):
                return [str(e).strip() for e in result if e and str(e).strip()]
        except json.JSONDecodeError:
            pass

    return []