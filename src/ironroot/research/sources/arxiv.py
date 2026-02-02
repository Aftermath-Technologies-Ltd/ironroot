# Author: Bradley R. Kinnard
"""arXiv API integration for preprint search."""

import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx


@dataclass
class ArxivPaper:
    """A paper from arXiv."""
    arxiv_id: str
    title: str
    abstract: str
    authors: list[str]
    published: str
    updated: str
    categories: list[str]
    pdf_url: str
    abs_url: str
    primary_category: str


@dataclass
class ArxivSearchResult:
    """Search results from arXiv."""
    papers: list[ArxivPaper]
    total: int
    query: str
    data_hash: str
    retrieved_at: str


class ArxivSource:
    """Client for arXiv API.

    Free and unlimited, but be respectful with rate limiting.
    See: https://arxiv.org/help/api/
    """

    BASE_URL = "https://export.arxiv.org/api/query"
    ATOM_NS = "{http://www.w3.org/2005/Atom}"
    ARXIV_NS = "{http://arxiv.org/schemas/atom}"

    def __init__(self):
        self._client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)

    async def search(
        self,
        query: str,
        max_results: int = 10,
        sort_by: str = "relevance",
        sort_order: str = "descending",
        categories: list[str] | None = None,
    ) -> ArxivSearchResult:
        """Search arXiv for papers.

        Args:
            query: Search query (supports arXiv query syntax)
            max_results: Max papers to return
            sort_by: "relevance", "lastUpdatedDate", or "submittedDate"
            sort_order: "ascending" or "descending"
            categories: Filter by arXiv categories (e.g., ["cs.AI", "cs.LG"])
        """
        # Build search query
        search_query = f"all:{query}"
        if categories:
            cat_query = " OR ".join(f"cat:{cat}" for cat in categories)
            search_query = f"({search_query}) AND ({cat_query})"

        params = {
            "search_query": search_query,
            "start": 0,
            "max_results": max_results,
            "sortBy": sort_by,
            "sortOrder": sort_order,
        }

        response = await self._client.get(self.BASE_URL, params=params)
        response.raise_for_status()

        # Parse Atom XML
        papers = self._parse_response(response.text)

        # Get total from feed
        root = ET.fromstring(response.text)
        total_elem = root.find(f"{self.ATOM_NS}totalResults",
                               namespaces={"opensearch": "http://a9.com/-/spec/opensearch/1.1/"})
        total = int(total_elem.text) if total_elem is not None else len(papers)

        data_hash = hashlib.sha256(response.text.encode()).hexdigest()[:16]

        return ArxivSearchResult(
            papers=papers,
            total=total,
            query=query,
            data_hash=data_hash,
            retrieved_at=datetime.now(timezone.utc).isoformat(),
        )

    def _parse_response(self, xml_text: str) -> list[ArxivPaper]:
        """Parse arXiv Atom XML response."""
        root = ET.fromstring(xml_text)
        papers = []

        for entry in root.findall(f"{self.ATOM_NS}entry"):
            # Extract arxiv ID from the id URL
            id_elem = entry.find(f"{self.ATOM_NS}id")
            arxiv_url = id_elem.text if id_elem is not None else ""
            arxiv_id = arxiv_url.split("/abs/")[-1] if "/abs/" in arxiv_url else ""

            # Title (clean whitespace)
            title_elem = entry.find(f"{self.ATOM_NS}title")
            title = " ".join(title_elem.text.split()) if title_elem is not None and title_elem.text else ""

            # Abstract (clean whitespace)
            summary_elem = entry.find(f"{self.ATOM_NS}summary")
            abstract = " ".join(summary_elem.text.split()) if summary_elem is not None and summary_elem.text else ""

            # Authors
            authors = []
            for author in entry.findall(f"{self.ATOM_NS}author"):
                name_elem = author.find(f"{self.ATOM_NS}name")
                if name_elem is not None and name_elem.text:
                    authors.append(name_elem.text)

            # Dates
            published_elem = entry.find(f"{self.ATOM_NS}published")
            published = published_elem.text if published_elem is not None else ""

            updated_elem = entry.find(f"{self.ATOM_NS}updated")
            updated = updated_elem.text if updated_elem is not None else ""

            # Categories
            categories = []
            primary_category = ""
            for cat in entry.findall(f"{self.ARXIV_NS}primary_category"):
                term = cat.get("term", "")
                if term:
                    primary_category = term
                    categories.append(term)
            for cat in entry.findall(f"{self.ATOM_NS}category"):
                term = cat.get("term", "")
                if term and term not in categories:
                    categories.append(term)

            # Links
            pdf_url = ""
            abs_url = arxiv_url
            for link in entry.findall(f"{self.ATOM_NS}link"):
                if link.get("type") == "application/pdf":
                    pdf_url = link.get("href", "")

            papers.append(ArxivPaper(
                arxiv_id=arxiv_id,
                title=title,
                abstract=abstract,
                authors=authors,
                published=published,
                updated=updated,
                categories=categories,
                pdf_url=pdf_url,
                abs_url=abs_url,
                primary_category=primary_category,
            ))

        return papers

    async def get_paper(self, arxiv_id: str) -> ArxivPaper | None:
        """Get a specific paper by arXiv ID."""
        # Clean the ID (remove version if present for search)
        clean_id = re.sub(r"v\d+$", "", arxiv_id)

        params = {
            "id_list": clean_id,
            "max_results": 1,
        }

        response = await self._client.get(self.BASE_URL, params=params)
        response.raise_for_status()

        papers = self._parse_response(response.text)
        return papers[0] if papers else None

    async def health_check(self) -> bool:
        """Check if arXiv API is accessible."""
        try:
            params = {"search_query": "all:test", "max_results": 1}
            response = await self._client.get(self.BASE_URL, params=params)
            return response.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
