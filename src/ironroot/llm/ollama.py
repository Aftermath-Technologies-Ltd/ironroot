# Author: Bradley R. Kinnard
"""Ollama client for local LLM inference."""

import os

import httpx

from ironroot.llm.client import LLMClient, LLMResponse


class OllamaClient(LLMClient):
    """Client for local Ollama LLM inference."""

    def __init__(
        self,
        host: str | None = None,
        model: str | None = None,
    ):
        raw_host = host or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        # Ensure host has http:// prefix
        if not raw_host.startswith("http://") and not raw_host.startswith("https://"):
            raw_host = f"http://{raw_host}"
        self.host = raw_host
        self.model = model or os.getenv("OLLAMA_MODEL", "llama3.2:8b")
        self._client = httpx.AsyncClient(
            base_url=self.host,
            timeout=300.0,  # Local inference can be slow
        )

    async def complete(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """Generate a completion using local Ollama."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = await self._client.post(
            "/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
            },
        )
        response.raise_for_status()
        data = response.json()

        return LLMResponse(
            content=data["message"]["content"],
            model=data.get("model", self.model),
            usage={
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
            },
            raw_response=data,
        )

    async def complete_with_search(
        self,
        query: str,
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Ollama doesn't have web search - falls back to regular completion.

        For hybrid mode, use GrokClient for search queries.
        """
        search_system = system or "You are a research assistant. Answer based on your training knowledge."
        return await self.complete(
            query,
            system=search_system,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def health_check(self) -> bool:
        """Check if Ollama is running and model is available."""
        try:
            response = await self._client.get("/api/tags")
            if response.status_code != 200:
                return False
            data = response.json()
            models = [m["name"] for m in data.get("models", [])]
            # Check if our model or a variant is available
            model_base = self.model.split(":")[0]
            return any(model_base in m for m in models)
        except Exception:
            return False

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
