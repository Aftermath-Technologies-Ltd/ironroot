# Author: Bradley R. Kinnard
"""LLM integration for IRONROOT research system."""

from ironroot.llm.client import LLMClient, get_llm_client
from ironroot.llm.grok import GrokClient
from ironroot.llm.ollama import OllamaClient

__all__ = ["GrokClient", "LLMClient", "OllamaClient", "get_llm_client"]
