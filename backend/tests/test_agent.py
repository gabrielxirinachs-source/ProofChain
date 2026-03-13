"""

Tests for the LangGraph agent loop.

The agent has LLM calls and external API calls, so most tests
use mocking to test the logic without making real API calls.

Key testing patterns:
  - Mock LLM responses to test routing logic
  - Test each node in isolation
  - Integration test runs the full graph end-to-end
"""
import pytest
import uuid
from unittest.mock import AsyncMock, patch, MagicMock

from app.agents.state import initial_state, AgentState
from app.agents.graph import route_after_plan, route_after_evaluate


# ── State Tests ───────────────────────────────────────────────────────────────

class TestInitialState:
    def test_initial_state_has_correct_defaults(self):
        state = initial_state("The Eiffel Tower is 330 meters tall")
        assert state["claim_text"] == "The Eiffel Tower is 330 meters tall"
        assert state["evidence_nodes"] == []
        assert state["sources"] == []
        assert state["iterations"] == 0
        assert state["next_action"] == "plan"
        assert state["verdict"] is None
        assert state["confidence"] is None
        assert state["evidence_sufficient"] is False

    def test_initial_state_has_empty_lists(self):
        state = initial_state("Some claim")
        assert state["search_queries"] == []
        assert state["entities_searched"] == []
        assert state["failure_modes"] == []


# ── Routing Tests ─────────────────────────────────────────────────────────────

class TestRouteAfterPlan:
    """Test the conditional routing logic after the plan node."""

    def make_state(self, next_action: str, iterations: int = 0) -> AgentState:
        state = initial_state("test claim")
        state["next_action"] = next_action
        state["iterations"] = iterations
        return state

    def test_routes_to_wikidata(self):
        state = self.make_state("wikidata")
        assert route_after_plan(state) == "node_wikidata"

    def test_routes_to_web_search(self):
        state = self.make_state("web_search")
        assert route_after_plan(state) == "node_web_search"

    def test_routes_to_evaluate(self):
        state = self.make_state("evaluate")
        assert route_after_plan(state) == "node_evaluate"

    def test_routes_to_verdict(self):
        state = self.make_state("verdict")
        assert route_after_plan(state) == "node_verdict"

    def test_forces_verdict_at_max_iterations(self):
        """Agent must stop at MAX_AGENT_ITERATIONS regardless of next_action."""
        from app.core.config import get_settings
        max_iter = get_settings().MAX_AGENT_ITERATIONS
        state = self.make_state("wikidata", iterations=max_iter)
        assert route_after_plan(state) == "node_verdict"

    def test_unknown_action_defaults_to_evaluate(self):
        state = self.make_state("unknown_action")
        assert route_after_plan(state) == "node_evaluate"


class TestRouteAfterEvaluate:
    """Test the conditional routing logic after the evaluate node."""

    def test_goes_to_verdict_when_sufficient(self):
        state = initial_state("test claim")
        state["evidence_sufficient"] = True
        state["iterations"] = 2
        assert route_after_evaluate(state) == "node_verdict"

    def test_loops_back_to_plan_when_insufficient(self):
        state = initial_state("test claim")
        state["evidence_sufficient"] = False
        state["iterations"] = 2
        assert route_after_evaluate(state) == "node_plan"

    def test_forces_verdict_near_iteration_limit(self):
        from app.core.config import get_settings
        max_iter = get_settings().MAX_AGENT_ITERATIONS
        state = initial_state("test claim")
        state["evidence_sufficient"] = False
        state["iterations"] = max_iter - 1
        assert route_after_evaluate(state) == "node_verdict"


# ── Node Tests ────────────────────────────────────────────────────────────────

class TestPlanNode:
    """Test the plan node with mocked LLM."""

    async def test_plan_node_returns_valid_action(self):
        from app.agents.nodes import plan_node

        mock_response = MagicMock()
        mock_response.choices[0].message.content = "wikidata"

        with patch("app.agents.nodes.AsyncOpenAI") as mock_openai:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                return_value=mock_response
            )
            mock_openai.return_value = mock_client

            state = initial_state("The Eiffel Tower is 330 meters tall")
            result = await plan_node(state)

        assert result["next_action"] == "wikidata"
        assert result["iterations"] == 1

    async def test_plan_node_increments_iterations(self):
        from app.agents.nodes import plan_node

        mock_response = MagicMock()
        mock_response.choices[0].message.content = "evaluate"

        with patch("app.agents.nodes.AsyncOpenAI") as mock_openai:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                return_value=mock_response
            )
            mock_openai.return_value = mock_client

            state = initial_state("test claim")
            state["iterations"] = 3
            result = await plan_node(state)

        assert result["iterations"] == 4

    async def test_plan_node_handles_invalid_llm_response(self):
        """If LLM returns garbage, should default to evaluate."""
        from app.agents.nodes import plan_node

        mock_response = MagicMock()
        mock_response.choices[0].message.content = "I don't know what to do"

        with patch("app.agents.nodes.AsyncOpenAI") as mock_openai:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                return_value=mock_response
            )
            mock_openai.return_value = mock_client

            state = initial_state("test claim")
            result = await plan_node(state)

        assert result["next_action"] == "evaluate"


class TestEvaluateNode:
    """Test the evaluate node with mocked LLM."""

    async def test_evaluate_returns_sufficient_true(self):
        from app.agents.nodes import evaluate_node

        mock_response = MagicMock()
        mock_response.choices[0].message.content = (
            '{"sufficient": true, "reasoning": "Strong evidence found", "gaps": []}'
        )

        with patch("app.agents.nodes.AsyncOpenAI") as mock_openai:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                return_value=mock_response
            )
            mock_openai.return_value = mock_client

            state = initial_state("test claim")
            result = await evaluate_node(state)

        assert result["evidence_sufficient"] is True
        assert "Strong evidence" in result["evaluation_reasoning"]

    async def test_evaluate_returns_sufficient_false(self):
        from app.agents.nodes import evaluate_node

        mock_response = MagicMock()
        mock_response.choices[0].message.content = (
            '{"sufficient": false, "reasoning": "Need more sources", "gaps": ["recent data"]}'
        )

        with patch("app.agents.nodes.AsyncOpenAI") as mock_openai:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                return_value=mock_response
            )
            mock_openai.return_value = mock_client

            state = initial_state("test claim")
            result = await evaluate_node(state)

        assert result["evidence_sufficient"] is False


# ── Integration Test ──────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.skipif(
    not __import__('os').environ.get('OPENAI_API_KEY', '').startswith('sk-') or
    __import__('os').environ.get('OPENAI_API_KEY', '') == 'sk-test-placeholder',
    reason="Requires a real OpenAI API key"
)
async def test_full_agent_run():
    """
    Run the complete agent loop on a real claim.
    Requires OpenAI API key + internet access.
    """
    from app.agents.graph import run_fact_check

    result = await run_fact_check("The Eiffel Tower is located in Paris, France")

    assert result["verdict"] is not None
    assert result["verdict"] in [
        "supported", "contradicted", "partially_supported",
        "insufficient", "unverifiable"
    ]
    assert result["confidence"] is not None
    assert 0.0 <= result["confidence"] <= 1.0
    assert len(result["evidence_nodes"]) > 0