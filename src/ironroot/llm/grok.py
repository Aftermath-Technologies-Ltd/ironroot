# Author: Bradley R. Kinnard
"""xAI Grok API client with web search capabilities."""

import os
from typing import Any

import httpx

from ironroot.llm.client import Citation, LLMClient, LLMResponse


class GrokClient(LLMClient):
    """Client for xAI Grok API with web search and reasoning."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "grok-4-1-fast-reasoning",
        base_url: str = "https://api.x.ai/v1",
    ):
        self.api_key = api_key or os.getenv("XAI_API_KEY")
        if not self.api_key:
            raise ValueError("XAI_API_KEY not set")
        self.model = model
        self.base_url = base_url
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=120.0,
        )

    async def complete(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """Generate a completion without web search."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = await self._client.post(
            "/chat/completions",
            json={
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        response.raise_for_status()
        data = response.json()

        return LLMResponse(
            content=data["choices"][0]["message"]["content"],
            model=data.get("model", self.model),
            usage=data.get("usage", {}),
            raw_response=data,
        )

    async def complete_with_search(
        self,
        query: str,
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Generate a completion with web search enabled.

        Uses Grok's agentic web search to find and cite real sources.
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": query})

        # Enable web search tool
        response = await self._client.post(
            "/chat/completions",
            json={
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "tools": [
                    {
                        "type": "web_search",
                        "web_search": {},
                    }
                ],
            },
        )
        response.raise_for_status()
        data = response.json()

        # Extract citations from response
        citations = []
        if "citations" in data:
            for cite in data["citations"]:
                citations.append(Citation(
                    url=cite.get("url", ""),
                    title=cite.get("title"),
                    snippet=cite.get("snippet"),
                ))

        return LLMResponse(
            content=data["choices"][0]["message"]["content"],
            model=data.get("model", self.model),
            citations=citations,
            usage=data.get("usage", {}),
            raw_response=data,
        )

    async def search_academic(
        self,
        query: str,
        max_results: int = 10,
    ) -> LLMResponse:
        """Search for academic information with web search focused on scholarly sources."""
        system = """You are a research assistant. Search for academic and scholarly information
        about the given topic. Focus on peer-reviewed papers, research studies, and authoritative
        sources. Provide detailed findings with citations."""

        search_prompt = f"""Search for academic research and scholarly sources on: {query}

        For each finding:
        1. Cite the source with URL
        2. Summarize the key claims or findings
        3. Note the methodology if mentioned
        4. Indicate the year and authors if available

        Focus on peer-reviewed and authoritative sources."""

        return await self.complete_with_search(
            search_prompt,
            system=system,
            temperature=0.2,
            max_tokens=4096,
        )

    async def health_check(self) -> bool:
        """Check if Grok API is accessible."""
        try:
            response = await self._client.get("/models")
            return response.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
