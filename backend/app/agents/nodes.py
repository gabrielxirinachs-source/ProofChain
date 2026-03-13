"""

Each function here is a NODE in the LangGraph state graph.
A node receives the current AgentState, does work, and returns
a dict of state updates (only the fields it changed).

Node overview:
  plan_node      → LLM decides what action to take next
  wikidata_node  → queries Wikidata KG for structured facts
  web_search_node → searches web + fetches pages
  evaluate_node  → LLM judges if evidence is sufficient
  verdict_node   → LLM produces final verdict + confidence

The MDP framing:
  State   = AgentState (evidence collected so far + claim)
  Actions = {wikidata, web_search, evaluate, verdict}
  Policy  = plan_node (LLM decides best action given state)
  Terminal = evidence_sufficient=True OR iterations >= MAX
"""
import json
from openai import AsyncOpenAI

from app.agents.state import AgentState
from app.core.config import get_settings
from app.services.entity_extractor import extract_entities
from app.services.wikidata_client import retrieve_evidence_for_entity
from app.services.evidence_builder import (
    build_wikidata_source,
    build_evidence_nodes,
    deduplicate_facts,
)
from app.services.web_retriever import (
    search_and_fetch,
    page_to_source,
    page_to_evidence_nodes,
)

settings = get_settings()


# ── Plan Node ─────────────────────────────────────────────────────────────────

PLAN_PROMPT = """You are the planning component of a fact-checking agent.

Your job is to decide the NEXT action to take to gather evidence for verifying a claim.

Current state:
- Claim: {claim}
- Evidence collected so far: {evidence_count} pieces
- Entities already searched in Wikidata: {entities_searched}
- Web searches already done: {searches_done}
- Iterations completed: {iterations}/{max_iterations}

Available actions:
- "wikidata": Query the Wikidata knowledge graph for structured facts about named entities in the claim
- "web_search": Search the web for recent or detailed information about the claim
- "evaluate": Assess whether we have enough evidence to make a verdict
- "verdict": Produce the final verdict (only if evaluate said evidence is sufficient)

Decision rules:
1. Start with "wikidata" if there are named entities not yet searched
2. Use "web_search" if wikidata didn't return relevant facts OR claim involves recent events
3. Use "evaluate" after collecting at least 3 pieces of evidence OR after 2+ iterations
4. Use "verdict" only after evaluate confirms evidence is sufficient
5. Use "evaluate" if iterations >= {max_iterations} - 1 (approaching limit)

Respond with ONLY one of: "wikidata", "web_search", "evaluate", "verdict"
"""


async def plan_node(state: AgentState) -> dict:
    """
    LLM-powered planner that decides the next action.

    This is the "policy" in MDP terms — given the current state
    (what evidence we have, what we've tried), it selects the
    best next action.
    """
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    prompt = PLAN_PROMPT.format(
        claim=state["claim_text"],
        evidence_count=len(state["evidence_nodes"]),
        entities_searched=state["entities_searched"] or "none",
        searches_done=state["search_queries"] or "none",
        iterations=state["iterations"],
        max_iterations=settings.MAX_AGENT_ITERATIONS,
    )

    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=10,      # We only need one word
    )

    action = response.choices[0].message.content.strip().lower()

    # Validate — if LLM returns something unexpected, default to evaluate
    valid_actions = {"wikidata", "web_search", "evaluate", "verdict"}
    if action not in valid_actions:
        action = "evaluate"

    return {
        "next_action": action,
        "iterations": state["iterations"] + 1,
    }


# ── Wikidata Node ─────────────────────────────────────────────────────────────

async def wikidata_node(state: AgentState) -> dict:
    """
    Queries Wikidata for structured facts about entities in the claim.

    Flow:
      1. Extract entities from claim text using LLM
      2. Filter out entities we've already searched
      3. For each new entity: search Wikidata → get facts → build evidence nodes
      4. Return new evidence nodes + sources to add to state
    """
    # Extract entities from the claim
    entities = await extract_entities(state["claim_text"])

    # Only search entities we haven't tried yet
    new_entities = [
        e for e in entities
        if e not in state["entities_searched"]
    ]

    if not new_entities:
        # Nothing new to search — signal to try web search instead
        return {
            "next_action": "web_search",
            "entities_searched": [],
        }

    new_evidence_nodes = []
    new_sources = []
    searched = []

    for entity_name in new_entities[:3]:    # Max 3 entities per iteration
        entity, facts = await retrieve_evidence_for_entity(entity_name)

        if not entity or not facts:
            searched.append(entity_name)
            continue

        facts = deduplicate_facts(facts)

        # Build source object
        source = build_wikidata_source(entity)

        # We need a real UUID for source_id — use a placeholder here.
        # In production (Phase 6), we'll save to DB first and use real UUIDs.
        import uuid
        temp_source_id = uuid.uuid4()

        # Build evidence nodes
        nodes = build_evidence_nodes(facts, temp_source_id)

        new_sources.append(source)
        new_evidence_nodes.extend(nodes)
        searched.append(entity_name)

    return {
        "evidence_nodes": new_evidence_nodes,
        "sources": new_sources,
        "entities_searched": searched,
    }


# ── Web Search Node ───────────────────────────────────────────────────────────

async def web_search_node(state: AgentState) -> dict:
    """
    Searches the web and fetches pages to fill evidence gaps.

    Builds a targeted search query from the claim + what we already know,
    then fetches pages and converts them to evidence nodes.
    """
    # Build a focused search query from the claim
    # We append "fact check" to get more analytical content
    query = f"{state['claim_text']} fact check evidence"

    # Don't repeat searches we've already done
    if query in state["search_queries"]:
        # Try a different angle
        query = f"{state['claim_text']} source verification"

    if query in state["search_queries"]:
        # We've exhausted web search options
        return {"next_action": "evaluate"}

    pages = await search_and_fetch(query, max_pages=3)

    new_evidence_nodes = []
    new_sources = []

    import uuid
    for page in pages:
        source = page_to_source(page)
        temp_source_id = uuid.uuid4()
        nodes = page_to_evidence_nodes(page, temp_source_id, max_chunk_size=400)

        new_sources.append(source)
        new_evidence_nodes.extend(nodes[:5])    # Max 5 chunks per page

    return {
        "evidence_nodes": new_evidence_nodes,
        "sources": new_sources,
        "search_queries": [query],
    }


# ── Evaluate Node ─────────────────────────────────────────────────────────────

EVALUATE_PROMPT = """You are evaluating whether we have sufficient evidence to fact-check a claim.

Claim: {claim}

Evidence collected ({count} pieces):
{evidence_summary}

Is this evidence sufficient to make a confident verdict about the claim?

Consider:
- Do we have direct evidence that supports OR contradicts the claim?
- Is the evidence from reliable sources?
- Are there major gaps in the evidence?

Respond with a JSON object:
{{
  "sufficient": true or false,
  "reasoning": "brief explanation of why evidence is or isn't sufficient",
  "gaps": ["list of", "missing evidence", "if any"]
}}

Respond with ONLY the JSON object, no other text.
"""


async def evaluate_node(state: AgentState) -> dict:
    """
    LLM judge that evaluates whether we have enough evidence.

    This is the "reward signal" in MDP terms — it tells the agent
    whether the current state is good enough to terminate, or whether
    it should keep collecting evidence.
    """
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    # Summarize evidence for the prompt (first 100 chars of each node)
    evidence_summary = "\n".join([
        f"- {node.text[:150]}"
        for node in state["evidence_nodes"][:15]   # Cap at 15 to stay in context
    ]) or "No evidence collected yet."

    prompt = EVALUATE_PROMPT.format(
        claim=state["claim_text"],
        count=len(state["evidence_nodes"]),
        evidence_summary=evidence_summary,
    )

    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=300,
    )

    raw = response.choices[0].message.content.strip()

    # Parse response safely
    try:
        # Strip markdown fences if present
        clean = raw.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean)
        sufficient = bool(data.get("sufficient", False))
        reasoning = data.get("reasoning", "")
    except (json.JSONDecodeError, KeyError):
        sufficient = len(state["evidence_nodes"]) >= 5
        reasoning = "Could not parse evaluation — using evidence count heuristic."

    return {
        "evidence_sufficient": sufficient,
        "evaluation_reasoning": reasoning,
    }


# ── Verdict Node ──────────────────────────────────────────────────────────────

VERDICT_PROMPT = """You are a fact-checking judge. Analyze the evidence and produce a final verdict.

Claim: {claim}

Evidence ({count} pieces from {source_count} sources):
{evidence_summary}

Produce a verdict based strictly on the evidence provided.

Verdicts:
- "supported": Evidence clearly supports the claim
- "contradicted": Evidence clearly contradicts the claim
- "partially_supported": Evidence partially supports but with caveats
- "insufficient": Not enough evidence to make a determination
- "unverifiable": Claim cannot be verified (opinion, future event, etc.)

Respond with ONLY a JSON object:
{{
  "verdict": "one of the five verdicts above",
  "confidence": 0.0 to 1.0,
  "explanation": "2-3 sentence explanation citing specific evidence",
  "failure_modes": ["potential reason verdict could be wrong", "another reason"]
}}
"""


async def verdict_node(state: AgentState) -> dict:
    """
    Produces the final verdict based on all collected evidence.

    This is the terminal node — after this, the agent loop ends.
    It outputs the verdict, confidence score, explanation, and
    failure modes (ways the verdict could be wrong).
    """
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    evidence_summary = "\n".join([
        f"- [{node.kg_entity_id or 'web'}] {node.text[:200]}"
        for node in state["evidence_nodes"][:20]
    ]) or "No evidence collected."

    prompt = VERDICT_PROMPT.format(
        claim=state["claim_text"],
        count=len(state["evidence_nodes"]),
        source_count=len(state["sources"]),
        evidence_summary=evidence_summary,
    )

    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=500,
    )

    raw = response.choices[0].message.content.strip()

    try:
        clean = raw.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean)
        verdict = data.get("verdict", "insufficient")
        confidence = float(data.get("confidence", 0.5))
        explanation = data.get("explanation", "")
        failure_modes = data.get("failure_modes", [])
    except (json.JSONDecodeError, KeyError, ValueError):
        verdict = "insufficient"
        confidence = 0.0
        explanation = "Could not produce a structured verdict."
        failure_modes = ["Verdict generation failed"]

    return {
        "verdict": verdict,
        "confidence": confidence,
        "verdict_explanation": explanation,
        "failure_modes": failure_modes,
    }