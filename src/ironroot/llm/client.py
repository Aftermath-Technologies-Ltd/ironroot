# Author: Bradley R. Kinnard
"""Base LLM client interface and factory."""

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Citation:
    """A citation from web search."""

    url: str
    title: str | None = None
    snippet: str | None = None


@dataclass
class LLMResponse:
    """Response from an LLM call."""

    content: str
    model: str
    citations: list[Citation] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    raw_response: Any = None


class LLMClient(ABC):
    """Base interface for LLM clients."""

    @abstractmethod
    async def complete(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """Generate a completion from the LLM."""
        ...

    @abstractmethod
    async def complete_with_search(
        self,
        query: str,
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Generate a completion with web search (if supported)."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the LLM service is available."""
        ...


def get_llm_client() -> LLMClient:
    """Get the configured LLM client based on environment."""
    provider = os.getenv("LLM_PROVIDER", "hybrid").lower()

    if provider == "grok":
        from ironroot.llm.grok import GrokClient

        return GrokClient()
    elif provider == "ollama":
        from ironroot.llm.ollama import OllamaClient

        return OllamaClient()
    elif provider == "hybrid":
        from ironroot.llm.hybrid import HybridClient

        return HybridClient()
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")
