# Author: Bradley R. Kinnard
"""Hybrid LLM client: Grok for search, Ollama for synthesis."""

import os

from ironroot.llm.client import LLMClient, LLMResponse
from ironroot.llm.grok import GrokClient
from ironroot.llm.ollama import OllamaClient


class HybridClient(LLMClient):
    """Hybrid client using Grok for web search and Ollama for local synthesis.

    This approach:
    - Uses Grok's web search for gathering real-time data with citations
    - Uses local Ollama for synthesis, reducing API costs
    - Falls back gracefully if either service is unavailable
    """

    def __init__(self):
        self._grok: GrokClient | None = None
        self._ollama: OllamaClient | None = None
        self._grok_available: bool | None = None
        self._ollama_available: bool | None = None

    async def _get_grok(self) -> GrokClient | None:
        """Get Grok client if available."""
        if self._grok is None and os.getenv("XAI_API_KEY"):
            try:
                self._grok = GrokClient()
                self._grok_available = await self._grok.health_check()
            except Exception:
                self._grok_available = False
        return self._grok if self._grok_available else None

    async def _get_ollama(self) -> OllamaClient | None:
        """Get Ollama client if available."""
        if self._ollama is None:
            try:
                self._ollama = OllamaClient()
                self._ollama_available = await self._ollama.health_check()
            except Exception:
                self._ollama_available = False
        return self._ollama if self._ollama_available else None

    async def complete(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """Generate a completion, preferring local Ollama."""
        # Try Ollama first (cheaper, faster for local)
        ollama = await self._get_ollama()
        if ollama:
            return await ollama.complete(prompt, system, temperature, max_tokens)

        # Fall back to Grok
        grok = await self._get_grok()
        if grok:
            return await grok.complete(prompt, system, temperature, max_tokens)

        raise RuntimeError("No LLM available. Check Ollama is running or XAI_API_KEY is set.")

    async def complete_with_search(
        self,
        query: str,
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Generate a completion with web search using Grok."""
        grok = await self._get_grok()
        if grok:
            return await grok.complete_with_search(query, system, temperature, max_tokens)

        # Fall back to Ollama (no web search, but better than nothing)
        ollama = await self._get_ollama()
        if ollama:
            return await ollama.complete_with_search(query, system, temperature, max_tokens)

        raise RuntimeError("No LLM available for search. Set XAI_API_KEY for web search.")

    async def search_and_synthesize(
        self,
        query: str,
        synthesis_prompt: str | None = None,
    ) -> LLMResponse:
        """Search with Grok, synthesize with Ollama.

        This is the most cost-effective approach:
        1. Use Grok's web search to gather real data with citations
        2. Use local Ollama to synthesize/analyze the results
        """
        # Step 1: Search with Grok
        grok = await self._get_grok()
        if not grok:
            raise RuntimeError("Grok not available for web search")

        search_response = await grok.complete_with_search(query)

        # Step 2: Synthesize with Ollama (if available) or Grok
        ollama = await self._get_ollama()
        if ollama and synthesis_prompt:
            synthesis_input = f"""Based on the following research findings:

{search_response.content}

{synthesis_prompt}"""

            synth_response = await ollama.complete(
                synthesis_input,
                system="You are a research analyst synthesizing findings.",
                temperature=0.3,
            )

            # Combine: Ollama's synthesis with Grok's citations
            return LLMResponse(
                content=synth_response.content,
                model=f"hybrid:{grok.model}+{ollama.model}",
                citations=search_response.citations,
                usage={
                    "grok_tokens": search_response.usage,
                    "ollama_tokens": synth_response.usage,
                },
            )

        # No synthesis needed or Ollama unavailable
        return search_response

    async def health_check(self) -> bool:
        """Check if at least one LLM is available."""
        grok = await self._get_grok()
        ollama = await self._get_ollama()
        return grok is not None or ollama is not None

    async def close(self) -> None:
        """Close all clients."""
        if self._grok:
            await self._grok.close()
        if self._ollama:
            await self._ollama.close()
