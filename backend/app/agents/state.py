"""

The AgentState is the single source of truth that flows through
every node in the LangGraph agent loop.

Think of it like a baton in a relay race — each node receives it,
reads what's been done so far, adds its contribution, and passes
it to the next node.

Why TypedDict instead of a Pydantic model?
  LangGraph requires TypedDict for state definitions. It uses the
  type annotations to know how to merge state updates from parallel
  nodes (using the Annotated[list, operator.add] pattern for lists
  that should be accumulated, not replaced).
"""
import operator
from typing import TypedDict, Annotated
from app.models.evidence_node import EvidenceNode
from app.models.source import Source


class AgentState(TypedDict):
    """
    The complete state of the fact-checking agent at any point in time.

    Fields marked with Annotated[list, operator.add] are ACCUMULATED —
    each node appends to them rather than replacing them. This is how
    LangGraph handles list state across multiple loop iterations.

    Fields without Annotated are REPLACED — each node sets the latest value.
    """

    # ── Input ──────────────────────────────────────────────
    claim_text: str
    # The original claim being fact-checked. Never changes after initialization.

    # ── Accumulated Evidence ───────────────────────────────
    evidence_nodes: Annotated[list[EvidenceNode], operator.add]
    # All evidence nodes collected so far.
    # operator.add means new nodes are APPENDED, not replaced.

    sources: Annotated[list[Source], operator.add]
    # All sources retrieved so far. Same accumulation pattern.

    # ── Agent Control ──────────────────────────────────────
    iterations: int
    # How many times the agent has looped. Used to enforce MAX_AGENT_ITERATIONS.

    next_action: str
    # What the planner decided to do next.
    # One of: "wikidata", "web_search", "evaluate", "verdict"

    search_queries: Annotated[list[str], operator.add]
    # Queries the agent has already tried — prevents redundant searches.

    entities_searched: Annotated[list[str], operator.add]
    # Wikidata entities already looked up — prevents redundant KG queries.

    # ── Evaluation ─────────────────────────────────────────
    evidence_sufficient: bool
    # Set by the evaluate node. True = we have enough to make a verdict.

    evaluation_reasoning: str
    # The evaluator's explanation of why evidence is/isn't sufficient.

    # ── Final Output ───────────────────────────────────────
    verdict: str | None
    # Final verdict: "supported", "contradicted", "partially_supported",
    # "insufficient", "unverifiable". None until the verdict node runs.

    confidence: float | None
    # 0.0–1.0 confidence in the verdict. None until verdict node runs.

    failure_modes: list[str]
    # List of reasons the verdict might be wrong.
    # e.g. ["Evidence may be outdated", "Only one source found"]

    # ── Evidence Diff ──────────────────────────────────────
    verdict_explanation: str | None
    # Human-readable explanation of what evidence drove the verdict.
    # This is the "show your work" output — key for the UI.


def initial_state(claim_text: str) -> AgentState:
    """
    Create the starting state for a new fact-checking run.

    All lists start empty, all flags start False/None.
    The agent loop will fill everything in.

    Args:
        claim_text: The claim to fact-check

    Returns:
        Fresh AgentState ready for the agent loop
    """
    return AgentState(
        claim_text=claim_text,
        evidence_nodes=[],
        sources=[],
        iterations=0,
        next_action="plan",         # Always start by planning
        search_queries=[],
        entities_searched=[],
        evidence_sufficient=False,
        evaluation_reasoning="",
        verdict=None,
        confidence=None,
        failure_modes=[],
        verdict_explanation=None,
    )