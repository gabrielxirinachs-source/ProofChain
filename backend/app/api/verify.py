"""
app/api/verify.py

The /verify endpoint — the main API surface of ProofChain.

This is where all previous phases come together:
  - Phase 2: evidence nodes + sources (data models)
  - Phase 3: Wikidata retrieval (via agent)
  - Phase 4: web retrieval (via agent)
  - Phase 5: LangGraph agent loop
  - Phase 6: this file — the API layer + caching

Request flow:
  1. Receive claim text
  2. Check Redis cache — return instantly if found
  3. Run the LangGraph agent loop
  4. Convert agent state → API response schema
  5. Cache the result
  6. Return to caller
"""
import time
import uuid
from fastapi import APIRouter, HTTPException, status

from app.api.schemas import (
    VerifyRequest,
    VerifyResponse,
    EvidenceNodeSchema,
    EvidenceEdgeSchema,
    EvidenceGraphSchema,
    CitationSchema,
)
from app.agents.graph import run_fact_check
from app.agents.state import AgentState
from app.models.evidence_edge import EdgeRelationType
from app.services.cache import get_cached_result, set_cached_result

router = APIRouter()


@router.post(
    "/api/v1/verify",
    response_model=VerifyResponse,
    summary="Fact-check a claim",
    description="""
    Submit a claim to ProofChain for fact-checking.

    The agent will:
    1. Extract named entities from the claim
    2. Query Wikidata for structured facts
    3. Search the web for additional evidence
    4. Evaluate evidence sufficiency
    5. Return a verdict with full evidence graph

    Results are cached for 1 hour — repeated calls return instantly.
    """,
    responses={
        200: {"description": "Verification result with evidence graph"},
        400: {"description": "Invalid claim text"},
        500: {"description": "Agent loop failed"},
    }
)
async def verify_claim(request: VerifyRequest) -> VerifyResponse:
    """
    Main fact-checking endpoint.

    Takes a claim, runs the full multi-agent evidence pipeline,
    and returns a structured verdict with an auditable evidence graph.
    """
    start_time = time.time()

    # ── Step 1: Check Cache ───────────────────────────────
    cached = await get_cached_result(request.claim)
    if cached:
        # Return cached result with cached=True flag
        cached["cached"] = True
        cached["processing_time_ms"] = round((time.time() - start_time) * 1000, 2)
        return VerifyResponse(**cached)

    # ── Step 2: Run Agent Loop ────────────────────────────
    try:
        agent_state = await run_fact_check(request.claim)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent loop failed: {str(e)}",
        )

    # ── Step 3: Validate Agent Output ────────────────────
    if not agent_state.get("verdict"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Agent completed but produced no verdict",
        )

    # ── Step 4: Build Response ────────────────────────────
    response = _build_response(
        claim=request.claim,
        state=agent_state,
        processing_time_ms=round((time.time() - start_time) * 1000, 2),
    )

    # ── Step 5: Cache Result ──────────────────────────────
    await set_cached_result(request.claim, response.model_dump())

    return response


def _build_response(
    claim: str,
    state: AgentState,
    processing_time_ms: float,
) -> VerifyResponse:
    """
    Convert an AgentState into a VerifyResponse.

    This is the "translation layer" between the agent's internal
    state and the clean API contract we expose to callers.

    Args:
        claim:              The original claim text
        state:              Final AgentState from the agent loop
        processing_time_ms: How long the verification took

    Returns:
        VerifyResponse ready to serialize to JSON
    """
    evidence_nodes = state.get("evidence_nodes", [])
    sources = state.get("sources", [])

    # Build a source lookup by index for evidence nodes
    # (since we used temp UUIDs in the agent, we match by position)
    source_by_id = {}
    for source in sources:
        if hasattr(source, 'url'):
            source_by_id[source.url] = source

    # ── Build Evidence Node Schemas ───────────────────────
    node_schemas = []
    for i, node in enumerate(evidence_nodes):
        # Find the matching source by source attributes
        source_url = None
        source_type = None
        source_domain = None

        if node.attributes:
            source_url = node.attributes.get("source_url")

        # Try to find source from our sources list
        matching_source = None
        for source in sources:
            if hasattr(source, 'url') and source_url and source.url == source_url:
                matching_source = source
                break
            elif node.kg_entity_id and hasattr(source, 'url') and 'wikidata' in (source.url or ''):
                matching_source = source
                break

        if matching_source:
            source_url = source_url or matching_source.url
            source_type = str(matching_source.source_type) if matching_source.source_type else None
            source_domain = matching_source.domain

        node_schemas.append(EvidenceNodeSchema(
            id=str(uuid.uuid4()),   # Generate display ID
            text=node.text,
            kg_entity_id=node.kg_entity_id,
            kg_property_id=node.kg_property_id,
            attributes=node.attributes,
            retrieved_at=node.retrieved_at if hasattr(node, 'retrieved_at') else None,
            source_url=source_url,
            source_type=source_type,
            source_domain=source_domain,
        ))

    # ── Build Evidence Edge Schemas ───────────────────────
    # Since we don't have explicit edges from the agent yet
    # (those come in Phase 6 DB integration), we infer edges
    # from the verdict + evidence relationship
    edge_schemas = []
    verdict = state.get("verdict", "insufficient")
    explanation = state.get("verdict_explanation", "")

    for node_schema in node_schemas:
        # Determine relation type based on verdict
        # This is a simplification — Phase 6 DB will store real edges
        if verdict == "supported":
            relation = EdgeRelationType.SUPPORTED_BY
            support_score = state.get("confidence", 0.5)
        elif verdict == "contradicted":
            relation = EdgeRelationType.CONTRADICTED_BY
            support_score = -(state.get("confidence", 0.5))
        elif verdict == "partially_supported":
            relation = EdgeRelationType.PARTIALLY_SUPPORTS
            support_score = state.get("confidence", 0.5) * 0.5
        else:
            relation = EdgeRelationType.CONTEXT
            support_score = 0.0

        edge_schemas.append(EvidenceEdgeSchema(
            id=str(uuid.uuid4()),
            relation_type=relation.value,
            relevance_score=0.7,    # Placeholder — real scoring in Phase 6
            support_score=support_score,
            reasoning=explanation,
            evidence_node_id=node_schema.id,
        ))

    # ── Count Supporting vs Contradicting ─────────────────
    supporting = sum(
        1 for e in edge_schemas
        if e.relation_type in ("supported_by", "partially_supports")
    )
    contradicting = sum(
        1 for e in edge_schemas
        if e.relation_type == "contradicted_by"
    )

    # ── Build Evidence Graph ──────────────────────────────
    evidence_graph = EvidenceGraphSchema(
        nodes=node_schemas,
        edges=edge_schemas,
        node_count=len(node_schemas),
        supporting_count=supporting,
        contradicting_count=contradicting,
    )

    # ── Build Citations ───────────────────────────────────
    citations = []
    seen_urls = set()
    for source in sources:
        if not hasattr(source, 'url') or source.url in seen_urls:
            continue
        seen_urls.add(source.url)
        citations.append(CitationSchema(
            url=source.url,
            title=source.title,
            domain=source.domain,
            source_type=str(source.source_type) if source.source_type else "web",
            reliability_score=source.reliability_score,
        ))

    return VerifyResponse(
        claim=claim,
        verdict=verdict,
        confidence=state.get("confidence", 0.0),
        verdict_explanation=state.get("verdict_explanation"),
        evidence_graph=evidence_graph,
        citations=citations,
        failure_modes=state.get("failure_modes", []),
        iterations_used=state.get("iterations", 0),
        cached=False,
        processing_time_ms=processing_time_ms,
    )