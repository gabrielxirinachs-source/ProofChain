"""

Tests for the web retrieval pipeline.

Same pattern as test_wikidata.py:
  - Unit tests: test logic without network calls
  - Integration tests: make real HTTP requests (marked @pytest.mark.integration)
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
import uuid

from app.services.web_retriever import (
    FetchedPage,
    _chunk_text,
    _classify_domain,
    _extract_ddgo_urls,
    page_to_source,
    page_to_evidence_nodes,
)
from app.models.source import SourceType


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_page(text: str = "Sample text. " * 20, domain: str = "example.com") -> FetchedPage:
    """Helper to create a FetchedPage for testing."""
    return FetchedPage(
        url=f"https://{domain}/article",
        title="Test Article",
        text=text,
        domain=domain,
        fetched_at=datetime.now(timezone.utc),
    )


# ── Unit Tests ────────────────────────────────────────────────────────────────

class TestChunkText:
    def test_short_text_is_single_chunk(self):
        text = "This is a short sentence."
        chunks = _chunk_text(text, max_size=500)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_long_text_is_split(self):
        # Create text longer than 500 chars
        text = "This is a sentence. " * 50   # ~1000 chars
        chunks = _chunk_text(text, max_size=500)
        assert len(chunks) > 1

    def test_chunks_dont_exceed_max_size_by_much(self):
        text = "Short sentence. " * 100
        chunks = _chunk_text(text, max_size=200)
        # Each chunk should be reasonably sized
        for chunk in chunks:
            # Allow some overflow for long sentences
            assert len(chunk) < 400

    def test_no_empty_chunks(self):
        text = "First sentence. Second sentence. Third sentence."
        chunks = _chunk_text(text, max_size=500)
        assert all(len(c.strip()) > 0 for c in chunks)


class TestClassifyDomain:
    def test_wikipedia(self):
        assert _classify_domain("en.wikipedia.org") == SourceType.WIKIPEDIA

    def test_news_sites(self):
        assert _classify_domain("reuters.com") == SourceType.NEWS
        assert _classify_domain("bbc.com") == SourceType.NEWS
        assert _classify_domain("nytimes.com") == SourceType.NEWS

    def test_academic(self):
        assert _classify_domain("arxiv.org") == SourceType.ACADEMIC

    def test_unknown_is_web(self):
        assert _classify_domain("someblog.com") == SourceType.WEB
        assert _classify_domain("randomsite.net") == SourceType.WEB


class TestPageToSource:
    def test_wikipedia_page_gets_correct_type(self):
        page = make_page(domain="en.wikipedia.org")
        page.url = "https://en.wikipedia.org/wiki/Eiffel_Tower"
        source = page_to_source(page)
        assert source.source_type == SourceType.WIKIPEDIA
        assert source.reliability_score == 0.85

    def test_news_page_gets_correct_type(self):
        page = make_page(domain="reuters.com")
        source = page_to_source(page)
        assert source.source_type == SourceType.NEWS
        assert source.reliability_score == 0.70

    def test_source_has_correct_domain(self):
        page = make_page(domain="bbc.com")
        source = page_to_source(page)
        assert source.domain == "bbc.com"

    def test_source_url_matches_page_url(self):
        page = make_page()
        source = page_to_source(page)
        assert source.url == page.url


class TestPageToEvidenceNodes:
    def test_creates_nodes_from_page(self):
        page = make_page(text="This is evidence. " * 30)
        nodes = page_to_evidence_nodes(page, uuid.uuid4())
        assert len(nodes) > 0

    def test_nodes_have_no_embedding(self):
        """Embeddings are set later in the agent loop."""
        page = make_page(text="Evidence text. " * 30)
        nodes = page_to_evidence_nodes(page, uuid.uuid4())
        assert all(n.embedding is None for n in nodes)

    def test_nodes_have_no_kg_entity(self):
        """Web content has no KG entity ID."""
        page = make_page(text="Web content here. " * 30)
        nodes = page_to_evidence_nodes(page, uuid.uuid4())
        assert all(n.kg_entity_id is None for n in nodes)

    def test_nodes_have_source_attributes(self):
        page = make_page(domain="reuters.com")
        nodes = page_to_evidence_nodes(page, uuid.uuid4())
        assert all("domain" in n.attributes for n in nodes)
        assert all(n.attributes["domain"] == "reuters.com" for n in nodes)

    def test_skips_tiny_chunks(self):
        """Chunks under 50 chars should be skipped."""
        page = make_page(text="Hi. " + "This is a longer sentence with more content. " * 20)
        nodes = page_to_evidence_nodes(page, uuid.uuid4())
        assert all(len(n.text) >= 50 for n in nodes)


class TestExtractDdgoUrls:
    def test_extracts_encoded_urls(self):
        """Test URL extraction from DDG's current HTML format."""
        fake_html = '''
        <a rel="nofollow" class="result__a" href="https://reuters.com/article/1">Reuters result</a>
        <a rel="nofollow" class="result__a" href="https://bbc.com/news/2">BBC result</a>
        '''
        urls = _extract_ddgo_urls(fake_html, max_results=5)
        assert any("reuters.com" in u for u in urls)
        assert any("bbc.com" in u for u in urls)

    def test_respects_max_results(self):
        fake_html = '\n'.join([
            f'<a href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fsite{i}.com">r</a>'
            for i in range(10)
        ])
        urls = _extract_ddgo_urls(fake_html, max_results=3)
        assert len(urls) <= 3

    def test_filters_duckduckgo_internal_links(self):
        fake_html = '<a href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fduckduckgo.com%2Fsettings">settings</a>'
        urls = _extract_ddgo_urls(fake_html, max_results=5)
        assert not any("duckduckgo.com" in u for u in urls)


# ── Integration Tests ─────────────────────────────────────────────────────────

@pytest.mark.integration
async def test_fetch_wikipedia_page():
    """Real HTTP fetch of Wikipedia — requires internet."""
    from app.services.web_retriever import fetch_page
    page = await fetch_page("https://en.wikipedia.org/wiki/Eiffel_Tower")

    assert page is not None
    assert len(page.text) > 500
    assert "Eiffel" in page.text
    assert page.domain == "en.wikipedia.org"


@pytest.mark.integration
async def test_search_returns_urls():
    """Real DuckDuckGo search — requires internet."""
    from app.services.web_retriever import search_web
    urls = await search_web("Eiffel Tower height meters", max_results=3)

    assert len(urls) > 0
    assert all(u.startswith("http") for u in urls)


@pytest.mark.integration
async def test_search_and_fetch_pipeline():
    """Full pipeline: search → fetch → evidence nodes."""
    from app.services.web_retriever import search_and_fetch
    pages = await search_and_fetch("Eiffel Tower height", max_pages=2)

    assert len(pages) > 0
    assert all(len(p.text) > 100 for p in pages)