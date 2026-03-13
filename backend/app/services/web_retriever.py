"""


Web retrieval service — fetches live web pages and extracts
clean article text to use as evidence for fact-checking.

Two retrieval strategies:
  1. Direct URL fetch  — when we have a specific URL to check
  2. Search + fetch    — when we need to find relevant pages for a claim

Why Playwright instead of just httpx/requests?
  Many modern news sites and web apps render content with JavaScript.
  A plain HTTP request gets you an empty shell. Playwright runs a real
  headless browser (Chromium) that executes JS and returns the full page.

Why trafilatura for text extraction?
  Raw HTML is full of noise: nav bars, ads, cookie banners, footers.
  trafilatura uses machine learning to identify the main article content
  and strips everything else — giving us clean, embedable text.

Why DuckDuckGo for search?
  It's free, requires no API key, and has no rate limits for reasonable use.
  Google/Bing require paid API keys. Perfect for a portfolio project.
"""
import asyncio
import httpx
import trafilatura
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse

from app.core.config import get_settings
from app.models.source import Source, SourceType
from app.models.evidence_node import EvidenceNode

settings = get_settings()

# DuckDuckGo HTML search endpoint — no API key needed
DDGO_SEARCH_URL = "https://html.duckduckgo.com/html/"

# Headers that make us look like a real browser
# Without these, many sites return 403 Forbidden
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


@dataclass
class FetchedPage:
    """
    Represents a successfully fetched and extracted web page.

    url:        The actual URL fetched (may differ from requested if redirected)
    title:      Page title extracted from HTML
    text:       Clean article text extracted by trafilatura
    domain:     e.g. "reuters.com"
    fetched_at: When we retrieved it
    """
    url: str
    title: str
    text: str
    domain: str
    fetched_at: datetime


async def fetch_page(url: str) -> FetchedPage | None:
    """
    Fetch a web page and extract its main article text.

    Uses httpx for the HTTP request (fast, async) and trafilatura
    for text extraction (ML-based, high quality).

    Args:
        url: Full URL to fetch, e.g. "https://en.wikipedia.org/wiki/Eiffel_Tower"

    Returns:
        FetchedPage with clean text, or None if fetch/extraction fails
    """
    try:
        async with httpx.AsyncClient(
            timeout=settings.WEB_FETCH_TIMEOUT_SEC,
            follow_redirects=True,
            headers=BROWSER_HEADERS,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            html = response.text

    except (httpx.HTTPError, httpx.TimeoutException) as e:
        print(f"[web_retriever] Failed to fetch {url}: {e}")
        return None

    # Extract clean text using trafilatura
    # include_comments=False: skip comment sections
    # include_tables=True: keep structured data from tables
    text = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=True,
        no_fallback=False,       # Use fallback extraction if main method fails
    )

    if not text or len(text.strip()) < 100:
        # Page didn't have enough extractable content
        return None

    # Extract title from HTML (trafilatura can do this too)
    metadata = trafilatura.extract_metadata(html)
    title = metadata.title if metadata and metadata.title else urlparse(url).netloc

    domain = urlparse(url).netloc.replace("www.", "")

    return FetchedPage(
        url=url,
        title=title or domain,
        text=text.strip(),
        domain=domain,
        fetched_at=datetime.now(timezone.utc),
    )


async def search_web(query: str, max_results: int = 5) -> list[str]:
    """
    Search DuckDuckGo and return a list of result URLs.

    We use DuckDuckGo's HTML endpoint (not their API) — it returns
    a standard HTML page with search results that we parse ourselves.

    Args:
        query:       Search query string
        max_results: Maximum number of URLs to return

    Returns:
        List of URLs from search results
    """
    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers=BROWSER_HEADERS,
        ) as client:
            response = await client.post(
                DDGO_SEARCH_URL,
                data={"q": query, "b": "", "kl": "us-en"},
            )
            response.raise_for_status()
            html = response.text

    except (httpx.HTTPError, httpx.TimeoutException) as e:
        print(f"[web_retriever] Search failed for '{query}': {e}")
        return []

    # Parse URLs from DuckDuckGo HTML results
    # DDG wraps result URLs in href="/l/?uddg=<encoded_url>"
    urls = _extract_ddgo_urls(html, max_results)
    return urls


def _extract_ddgo_urls(html: str, max_results: int) -> list[str]:
    """
    Extract result URLs from DuckDuckGo HTML response.

    DDG now uses direct href URLs in result__a anchor tags.

    Args:
        html:        Raw HTML from DuckDuckGo
        max_results: Max URLs to return

    Returns:
        List of result URLs
    """
    import re

    urls = []

    # DDG result links now look like:
    # <a rel="nofollow" class="result__a" href="https://example.com/article">
    pattern = r'class="result__a"[^>]*href="(https?://[^"]+)"'

    matches = re.findall(pattern, html)
    for url in matches:
        url = url.strip()
        if url and "duckduckgo.com" not in url and url not in urls:
            urls.append(url)
            if len(urls) >= max_results:
                break

    return urls


async def search_and_fetch(
    query: str,
    max_pages: int | None = None,
) -> list[FetchedPage]:
    """
    Search the web for a query and fetch the top results.

    This is the main entry point for web retrieval in the agent loop.
    It combines search + fetch into a single operation.

    Args:
        query:     Search query, e.g. "Eiffel Tower height meters"
        max_pages: Max pages to fetch (defaults to settings.MAX_WEB_SOURCES)

    Returns:
        List of FetchedPage objects with extracted text
    """
    max_pages = max_pages or settings.MAX_WEB_SOURCES

    # Step 1: Get search result URLs
    urls = await search_web(query, max_results=max_pages)

    if not urls:
        return []

    # Step 2: Fetch all pages concurrently
    # asyncio.gather runs all fetches in parallel — much faster than sequential
    # return_exceptions=True means one failed fetch doesn't crash the whole batch
    tasks = [fetch_page(url) for url in urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Filter out failures (None returns and exceptions)
    pages = [
        r for r in results
        if isinstance(r, FetchedPage) and r is not None
    ]

    return pages


# ── Evidence Conversion ───────────────────────────────────────────────────────

def page_to_source(page: FetchedPage) -> Source:
    """
    Convert a FetchedPage into a Source record.

    Determines the source type based on the domain:
    - wikipedia.org → WIKIPEDIA
    - known news domains → NEWS
    - everything else → WEB

    Args:
        page: Successfully fetched page

    Returns:
        Source object (not yet saved to DB)
    """
    # Classify source type by domain
    source_type = _classify_domain(page.domain)

    # Assign reliability score based on source type
    reliability_scores = {
        SourceType.WIKIPEDIA: 0.85,
        SourceType.NEWS: 0.70,
        SourceType.WEB: 0.50,
        SourceType.ACADEMIC: 0.90,
    }

    return Source(
        url=page.url,
        source_type=source_type,
        title=page.title,
        domain=page.domain,
        reliability_score=reliability_scores.get(source_type, 0.50),
        fetched_at=page.fetched_at,
    )


def _classify_domain(domain: str) -> SourceType:
    """Classify a domain into a SourceType."""
    domain = domain.lower()

    if "wikipedia.org" in domain:
        return SourceType.WIKIPEDIA

    if any(d in domain for d in [
        "arxiv.org", "pubmed.ncbi", "scholar.google",
        "jstor.org", "semanticscholar.org", "ncbi.nlm.nih.gov",
    ]):
        return SourceType.ACADEMIC

    if any(d in domain for d in [
        "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk",
        "nytimes.com", "washingtonpost.com", "theguardian.com",
        "bloomberg.com", "wsj.com", "ft.com", "economist.com",
        "npr.org", "cnn.com", "nbcnews.com", "abcnews.go.com",
        "cbsnews.com", "politico.com", "thehill.com",
    ]):
        return SourceType.NEWS

    return SourceType.WEB


def page_to_evidence_nodes(
    page: FetchedPage,
    source_id,
    max_chunk_size: int = 500,
) -> list[EvidenceNode]:
    """
    Split a page's text into chunks and create EvidenceNode objects.

    Why chunk the text?
      A full article might be 5,000 words. We can't embed the whole thing
      as a single vector — it loses specificity. Smaller chunks (500 chars)
      mean each evidence node represents a focused claim or fact.

      This is called "chunking" and is fundamental to RAG
      (Retrieval Augmented Generation) systems.

    Args:
        page:           FetchedPage with extracted text
        source_id:      UUID of the already-saved Source
        max_chunk_size: Max characters per evidence node

    Returns:
        List of EvidenceNode objects (not yet saved to DB)
    """
    chunks = _chunk_text(page.text, max_chunk_size)
    nodes = []

    for chunk in chunks:
        if len(chunk.strip()) < 50:  # Skip tiny chunks
            continue

        node = EvidenceNode(
            text=chunk.strip(),
            embedding=None,         # Set later in agent loop
            kg_entity_id=None,      # Web content has no KG entity
            kg_property_id=None,
            attributes={
                "source_url": page.url,
                "source_title": page.title,
                "domain": page.domain,
            },
            source_id=source_id,
            retrieved_at=page.fetched_at,
        )
        nodes.append(node)

    return nodes


def _chunk_text(text: str, max_size: int) -> list[str]:
    """
    Split text into chunks at sentence boundaries.

    We split at sentence boundaries (periods followed by spaces)
    rather than arbitrary character positions — this keeps each
    chunk semantically coherent.

    Args:
        text:     Full article text
        max_size: Target max characters per chunk

    Returns:
        List of text chunks
    """
    # Split into sentences first
    import re
    sentences = re.split(r'(?<=[.!?])\s+', text)

    chunks = []
    current_chunk = ""

    for sentence in sentences:
        # If adding this sentence would exceed max_size, save current chunk
        if len(current_chunk) + len(sentence) > max_size and current_chunk:
            chunks.append(current_chunk.strip())
            current_chunk = sentence
        else:
            current_chunk += " " + sentence if current_chunk else sentence

    # Don't forget the last chunk
    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks