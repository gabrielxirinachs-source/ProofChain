"""
tests/test_verify.py

Tests for the /verify endpoint and supporting services.

We mock the agent loop so tests don't require OpenAI or internet.
This lets us test the API contract (request validation, response
structure, caching logic) in complete isolation.
"""
import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.api.schemas import VerifyRequest


# ── Schema Tests ──────────────────────────────────────────────────────────────

class TestVerifyRequest:
    def test_valid_request(self):
        req = VerifyRequest(claim="The Eiffel Tower is 330 meters tall")
        assert req.claim == "The Eiffel Tower is 330 meters tall"
        assert req.max_iterations == 5  # default

    def test_custom_iterations(self):
        req = VerifyRequest(claim="Some claim to verify here", max_iterations=3)
        assert req.max_iterations == 3

    def test_claim_too_short(self):
        with pytest.raises(Exception):
            VerifyRequest(claim="short")

    def test_claim_too_long(self):
        with pytest.raises(Exception):
            VerifyRequest(claim="x" * 1001)

    def test_iterations_out_of_range(self):
        with pytest.raises(Exception):
            VerifyRequest(claim="Valid claim text here", max_iterations=99)


# ── Cache Tests ───────────────────────────────────────────────────────────────

class TestCacheKey:
    def test_same_claim_same_key(self):
        from app.services.cache import make_cache_key
        key1 = make_cache_key("The Eiffel Tower is 330 meters tall")
        key2 = make_cache_key("The Eiffel Tower is 330 meters tall")
        assert key1 == key2

    def test_case_insensitive(self):
        from app.services.cache import make_cache_key
        key1 = make_cache_key("The Eiffel Tower is 330 meters tall")
        key2 = make_cache_key("the eiffel tower is 330 meters tall")
        assert key1 == key2

    def test_different_claims_different_keys(self):
        from app.services.cache import make_cache_key
        key1 = make_cache_key("The Eiffel Tower is 330 meters tall")
        key2 = make_cache_key("The Eiffel Tower is in London")
        assert key1 != key2

    def test_key_has_correct_prefix(self):
        from app.services.cache import make_cache_key
        key = make_cache_key("some claim text here")
        assert key.startswith("proofchain:verify:")


# ── API Endpoint Tests ────────────────────────────────────────────────────────

def make_mock_agent_state(verdict: str = "supported", confidence: float = 0.9):
    """Helper to create a realistic mock agent state."""
    from app.agents.state import initial_state
    from app.models.evidence_node import EvidenceNode
    from app.models.source import Source, SourceType
    import uuid
    from datetime import datetime, timezone

    state = initial_state("test claim")
    state["verdict"] = verdict
    state["confidence"] = confidence
    state["verdict_explanation"] = "Test explanation"
    state["failure_modes"] = ["Test failure mode"]
    state["iterations"] = 3

    # Add a mock evidence node
    node = EvidenceNode(
        text="Test evidence text about the claim",
        kg_entity_id="Q123",
        kg_property_id="P456",
        attributes={"property_label": "test", "value": "test"},
        source_id=uuid.uuid4(),
        retrieved_at=datetime.now(timezone.utc),
    )
    state["evidence_nodes"] = [node]

    # Add a mock source
    source = Source(
        url="https://www.wikidata.org/wiki/Q123",
        source_type=SourceType.WIKIDATA,
        title="Wikidata: Test Entity",
        domain="wikidata.org",
        reliability_score=0.9,
    )
    state["sources"] = [source]

    return state


class TestVerifyEndpoint:
    async def test_verify_returns_200(self):
        """Endpoint should return 200 with valid claim."""
        mock_state = make_mock_agent_state()

        with patch("app.api.verify.run_fact_check", new_callable=AsyncMock) as mock_run, \
             patch("app.api.verify.get_cached_result", new_callable=AsyncMock) as mock_cache_get, \
             patch("app.api.verify.set_cached_result", new_callable=AsyncMock):

            mock_run.return_value = mock_state
            mock_cache_get.return_value = None  # No cache hit

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/v1/verify",
                    json={"claim": "The Eiffel Tower is 330 meters tall"}
                )

        assert response.status_code == 200

    async def test_verify_response_structure(self):
        """Response should have all required fields."""
        mock_state = make_mock_agent_state("supported", 0.92)

        with patch("app.api.verify.run_fact_check", new_callable=AsyncMock) as mock_run, \
             patch("app.api.verify.get_cached_result", new_callable=AsyncMock) as mock_cache_get, \
             patch("app.api.verify.set_cached_result", new_callable=AsyncMock):

            mock_run.return_value = mock_state
            mock_cache_get.return_value = None

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/v1/verify",
                    json={"claim": "The Eiffel Tower is 330 meters tall"}
                )

        data = response.json()
        assert "verdict" in data
        assert "confidence" in data
        assert "evidence_graph" in data
        assert "citations" in data
        assert "failure_modes" in data
        assert "iterations_used" in data
        assert "cached" in data

    async def test_verify_returns_correct_verdict(self):
        """Verdict in response should match what agent returned."""
        mock_state = make_mock_agent_state("contradicted", 0.85)

        with patch("app.api.verify.run_fact_check", new_callable=AsyncMock) as mock_run, \
             patch("app.api.verify.get_cached_result", new_callable=AsyncMock) as mock_cache_get, \
             patch("app.api.verify.set_cached_result", new_callable=AsyncMock):

            mock_run.return_value = mock_state
            mock_cache_get.return_value = None

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/v1/verify",
                    json={"claim": "The Eiffel Tower is 330 meters tall"}
                )

        data = response.json()
        assert data["verdict"] == "contradicted"
        assert data["confidence"] == 0.85

    async def test_verify_claim_too_short_returns_422(self):
        """Claim under 10 chars should return 422 Unprocessable Entity."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/verify",
                json={"claim": "short"}
            )
        assert response.status_code == 422

    async def test_verify_returns_cached_result(self):
        """If cache hit, should return cached=True without calling agent."""
        cached_response = {
            "claim": "The Eiffel Tower is 330 meters tall",
            "verdict": "supported",
            "confidence": 0.95,
            "verdict_explanation": "Cached explanation",
            "evidence_graph": {
                "nodes": [], "edges": [],
                "node_count": 0,
                "supporting_count": 0,
                "contradicting_count": 0,
            },
            "citations": [],
            "failure_modes": [],
            "iterations_used": 3,
            "cached": False,
            "processing_time_ms": 100.0,
        }

        with patch("app.api.verify.get_cached_result", new_callable=AsyncMock) as mock_cache_get, \
             patch("app.api.verify.run_fact_check", new_callable=AsyncMock) as mock_run:

            mock_cache_get.return_value = cached_response
            mock_run.return_value = None  # Should NOT be called

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/v1/verify",
                    json={"claim": "The Eiffel Tower is 330 meters tall"}
                )

        assert response.status_code == 200
        data = response.json()
        assert data["cached"] is True
        mock_run.assert_not_called()  # Agent should NOT have run