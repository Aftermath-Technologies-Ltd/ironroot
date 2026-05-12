# Author: Bradley R. Kinnard
"""Grok-powered web search for real-time research data."""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from ironroot.llm.grok import GrokClient


@dataclass
class WebSearchResult:
    """Result from Grok web search."""

    content: str
    citations: list[dict]
    query: str
    data_hash: str
    retrieved_at: str
    token_usage: dict


class GrokSearchSource:
    """Use Grok's agentic web search for real-time research data.

    This provides:
    - Real-time web search with citations
    - X/Twitter search for social discourse
    - Automatic source verification
    """

    def __init__(self, client: GrokClient | None = None):
        self._client = client
        self._owns_client = False

    async def _get_client(self) -> GrokClient:
        """Get or create Grok client."""
        if self._client is None:
            self._client = GrokClient()
            self._owns_client = True
        return self._client

    async def search(
        self,
        query: str,
        focus: str = "general",
        max_sources: int = 10,
    ) -> WebSearchResult:
        """Search the web for information on a topic.

        Args:
            query: The research query
            focus: Focus area - "general", "academic", "news", "technical"
            max_sources: Target number of sources to find
        """
        client = await self._get_client()

        # Craft search prompt based on focus
        if focus == "academic":
            system = """You are a research assistant searching for academic and scholarly information.
            Focus on peer-reviewed papers, research studies, and authoritative sources.
            Always cite your sources with URLs."""
            search_query = f"Find academic research and scholarly sources about: {query}"
        elif focus == "news":
            system = """You are a research assistant searching for recent news and developments.
            Focus on reliable news sources and recent events.
            Always cite your sources with URLs."""
            search_query = f"Find recent news and developments about: {query}"
        elif focus == "technical":
            system = """You are a technical research assistant.
            Focus on technical documentation, specifications, and implementation details.
            Always cite your sources with URLs."""
            search_query = f"Find technical information and documentation about: {query}"
        else:
            system = """You are a comprehensive research assistant.
            Search for reliable, diverse sources on the topic.
            Include academic, news, and technical sources where relevant.
            Always cite your sources with URLs."""
            search_query = f"Research the following topic comprehensively: {query}"

        search_query += f"\n\nFind at least {max_sources} different sources and summarize key findings from each."

        response = await client.complete_with_search(
            search_query,
            system=system,
            temperature=0.2,
            max_tokens=4096,
        )

        # Build citations list
        citations = [
            {
                "url": c.url,
                "title": c.title,
                "snippet": c.snippet,
            }
            for c in response.citations
        ]

        data_hash = hashlib.sha256(response.content.encode()).hexdigest()[:16]

        return WebSearchResult(
            content=response.content,
            citations=citations,
            query=query,
            data_hash=data_hash,
            retrieved_at=datetime.now(UTC).isoformat(),
            token_usage=response.usage,
        )

    async def search_academic(self, query: str) -> WebSearchResult:
        """Search for academic/scholarly information."""
        return await self.search(query, focus="academic")

    async def search_news(self, query: str) -> WebSearchResult:
        """Search for recent news and developments."""
        return await self.search(query, focus="news")

    async def search_technical(self, query: str) -> WebSearchResult:
        """Search for technical documentation and specs."""
        return await self.search(query, focus="technical")

    async def research_question(
        self,
        question: str,
        require_evidence: bool = True,
    ) -> WebSearchResult:
        """Research a specific question and find evidence.

        Args:
            question: The research question to answer
            require_evidence: Whether to require cited evidence
        """
        client = await self._get_client()

        system = """You are a rigorous research assistant. Your goal is to find evidence-based answers.

        For each claim you make:
        1. Cite the source with a URL
        2. Note the credibility of the source
        3. Indicate if there are conflicting findings

        Be explicit about what the evidence supports vs what is speculation."""

        prompt = f"""Research Question: {question}

        Please search for evidence to answer this question.

        Structure your response as:
        1. DIRECT ANSWER: A concise answer based on evidence
        2. SUPPORTING EVIDENCE: Key findings with citations
        3. CONFLICTING VIEWS: Any contradictory evidence (if exists)
        4. CONFIDENCE LEVEL: How confident are you based on available evidence?
        5. LIMITATIONS: What couldn't you find or verify?"""

        response = await client.complete_with_search(
            prompt,
            system=system,
            temperature=0.1,
            max_tokens=4096,
        )

        citations = [
            {"url": c.url, "title": c.title, "snippet": c.snippet} for c in response.citations
        ]

        data_hash = hashlib.sha256(response.content.encode()).hexdigest()[:16]

        return WebSearchResult(
            content=response.content,
            citations=citations,
            query=question,
            data_hash=data_hash,
            retrieved_at=datetime.now(UTC).isoformat(),
            token_usage=response.usage,
        )

    async def health_check(self) -> bool:
        """Check if Grok search is available."""
        try:
            client = await self._get_client()
            return await client.health_check()
        except Exception:
            return False

    async def close(self) -> None:
        """Close the client if we own it."""
        if self._owns_client and self._client:
            await self._client.close()
