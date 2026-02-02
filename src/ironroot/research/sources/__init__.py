# Author: Bradley R. Kinnard
"""Real data source integrations for IRONROOT research.

Connects to actual APIs:
- Semantic Scholar: Academic papers and citations
- arXiv: Preprints and technical papers
- Grok Web Search: Real-time web data with citations
"""

from ironroot.research.sources.semantic_scholar import SemanticScholarSource
from ironroot.research.sources.arxiv import ArxivSource
from ironroot.research.sources.grok_search import GrokSearchSource

__all__ = ["SemanticScholarSource", "ArxivSource", "GrokSearchSource"]
