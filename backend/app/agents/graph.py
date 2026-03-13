"""
app/agents/graph.py

Wires all nodes together into a LangGraph StateGraph.

Node naming note:
  LangGraph disallows node names that conflict with state keys.
  Our AgentState has fields: "verdict", "sources", "plan" etc.
  So we prefix node names with "node_" to avoid collisions.
"""
from langgraph.graph import StateGraph, END

from app.agents.state import AgentState, initial_state
from app.agents.nodes import (
    plan_node,
    wikidata_node,
    web_search_node,
    evaluate_node,
    verdict_node,
)
from app.core.config import get_settings

settings = get_settings()


def route_after_plan(state: AgentState) -> str:
    """
    Conditional routing function after the plan node.

    Returns the name of the next node to execute based on
    the next_action field set by plan_node.
    """
    if state["iterations"] >= settings.MAX_AGENT_ITERATIONS:
        return "node_verdict"

    action = state.get("next_action", "evaluate")

    routing = {
        "wikidata": "node_wikidata",
        "web_search": "node_web_search",
        "evaluate": "node_evaluate",
        "verdict": "node_verdict",
    }

    return routing.get(action, "node_evaluate")


def route_after_evaluate(state: AgentState) -> str:
    """
    Conditional routing after the evaluate node.

    Sufficient evidence → verdict
    Not sufficient → loop back to plan
    """
    if state["evidence_sufficient"]:
        return "node_verdict"

    if state["iterations"] >= settings.MAX_AGENT_ITERATIONS - 1:
        return "node_verdict"

    return "node_plan"


def build_graph() -> StateGraph:
    """
    Construct and compile the fact-checking agent graph.

    Node names are prefixed with "node_" to avoid conflicts
    with AgentState field names (LangGraph requirement).
    """
    graph = StateGraph(AgentState)

    # ── Register Nodes ────────────────────────────────────
    graph.add_node("node_plan", plan_node)
    graph.add_node("node_wikidata", wikidata_node)
    graph.add_node("node_web_search", web_search_node)
    graph.add_node("node_evaluate", evaluate_node)
    graph.add_node("node_verdict", verdict_node)

    # ── Entry Point ───────────────────────────────────────
    graph.set_entry_point("node_plan")

    # ── Conditional Edges from plan ───────────────────────
    graph.add_conditional_edges(
        "node_plan",
        route_after_plan,
        {
            "node_wikidata": "node_wikidata",
            "node_web_search": "node_web_search",
            "node_evaluate": "node_evaluate",
            "node_verdict": "node_verdict",
        }
    )

    # ── Fixed Edges back to plan ──────────────────────────
    graph.add_edge("node_wikidata", "node_plan")
    graph.add_edge("node_web_search", "node_plan")

    # ── Conditional Edge from evaluate ───────────────────
    graph.add_conditional_edges(
        "node_evaluate",
        route_after_evaluate,
        {
            "node_verdict": "node_verdict",
            "node_plan": "node_plan",
        }
    )

    # ── Terminal Edge ─────────────────────────────────────
    graph.add_edge("node_verdict", END)

    return graph.compile()


# Compile once at module load — reused for all requests
fact_check_graph = build_graph()


async def run_fact_check(claim_text: str) -> AgentState:
    """
    Run the full fact-checking pipeline for a claim.

    Args:
        claim_text: The claim to fact-check

    Returns:
        Final AgentState with verdict, confidence, evidence, sources
    """
    state = initial_state(claim_text)
    result = await fact_check_graph.ainvoke(state)
    return result