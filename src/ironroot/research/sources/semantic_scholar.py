# Author: Bradley R. Kinnard
"""Semantic Scholar API integration for academic paper search."""

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx


@dataclass
class Paper:
    """A paper from Semantic Scholar."""

    paper_id: str
    title: str
    abstract: str | None
    year: int | None
    authors: list[str]
    citation_count: int
    url: str
    venue: str | None = None
    fields_of_study: list[str] = field(default_factory=list)


@dataclass
class SearchResult:
    """Search results from Semantic Scholar."""

    papers: list[Paper]
    total: int
    query: str
    data_hash: str
    retrieved_at: str


class SemanticScholarSource:
    """Client for Semantic Scholar API.

    Free tier: 100 requests per 5 minutes without API key.
    See: https://api.semanticscholar.org/
    """

    BASE_URL = "https://api.semanticscholar.org/graph/v1"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key
        headers = {"Accept": "application/json"}
        if api_key:
            headers["x-api-key"] = api_key
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers=headers,
            timeout=30.0,
            follow_redirects=True,
        )

    async def search(
        self,
        query: str,
        limit: int = 10,
        fields_of_study: list[str] | None = None,
        year_range: tuple[int, int] | None = None,
    ) -> SearchResult:
        """Search for papers matching a query.

        Args:
            query: Search query string
            limit: Max papers to return (1-100)
            fields_of_study: Filter by field (e.g., "Computer Science")
            year_range: Filter by year range (start, end)
        """
        params = {
            "query": query,
            "limit": min(limit, 100),
            "fields": "paperId,title,abstract,year,authors,citationCount,url,venue,fieldsOfStudy",
        }

        if fields_of_study:
            params["fieldsOfStudy"] = ",".join(fields_of_study)
        if year_range:
            params["year"] = f"{year_range[0]}-{year_range[1]}"

        response = await self._client.get("/paper/search", params=params)
        response.raise_for_status()
        data = response.json()

        papers = []
        for item in data.get("data", []):
            papers.append(
                Paper(
                    paper_id=item["paperId"],
                    title=item.get("title", ""),
                    abstract=item.get("abstract"),
                    year=item.get("year"),
                    authors=[a.get("name", "") for a in item.get("authors", [])],
                    citation_count=item.get("citationCount", 0),
                    url=item.get(
                        "url", f"https://www.semanticscholar.org/paper/{item['paperId']}"
                    ),
                    venue=item.get("venue"),
                    fields_of_study=[
                        f.get("category", "") for f in item.get("fieldsOfStudy", []) if f
                    ],
                )
            )

        # Create hash of response for verification
        data_hash = hashlib.sha256(str(data).encode()).hexdigest()[:16]

        return SearchResult(
            papers=papers,
            total=data.get("total", len(papers)),
            query=query,
            data_hash=data_hash,
            retrieved_at=datetime.now(UTC).isoformat(),
        )

    async def get_paper(self, paper_id: str) -> Paper | None:
        """Get details of a specific paper."""
        params = {
            "fields": "paperId,title,abstract,year,authors,citationCount,url,venue,fieldsOfStudy",
        }
        response = await self._client.get(f"/paper/{paper_id}", params=params)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        item = response.json()

        return Paper(
            paper_id=item["paperId"],
            title=item.get("title", ""),
            abstract=item.get("abstract"),
            year=item.get("year"),
            authors=[a.get("name", "") for a in item.get("authors", [])],
            citation_count=item.get("citationCount", 0),
            url=item.get("url", f"https://www.semanticscholar.org/paper/{item['paperId']}"),
            venue=item.get("venue"),
            fields_of_study=[f.get("category", "") for f in item.get("fieldsOfStudy", []) if f],
        )

    async def get_citations(self, paper_id: str, limit: int = 10) -> list[Paper]:
        """Get papers that cite a given paper."""
        params = {
            "fields": "paperId,title,abstract,year,authors,citationCount,url",
            "limit": min(limit, 100),
        }
        response = await self._client.get(f"/paper/{paper_id}/citations", params=params)
        response.raise_for_status()
        data = response.json()

        papers = []
        for item in data.get("data", []):
            citing = item.get("citingPaper", {})
            if citing:
                papers.append(
                    Paper(
                        paper_id=citing["paperId"],
                        title=citing.get("title", ""),
                        abstract=citing.get("abstract"),
                        year=citing.get("year"),
                        authors=[a.get("name", "") for a in citing.get("authors", [])],
                        citation_count=citing.get("citationCount", 0),
                        url=citing.get("url", ""),
                    )
                )
        return papers

    async def health_check(self) -> bool:
        """Check if API is accessible."""
        try:
            response = await self._client.get(
                "/paper/search", params={"query": "test", "limit": 1}
            )
            return response.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
