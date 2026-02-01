# Author: Bradley R. Kinnard
"""Topic-relevant data sources for semantic research.

Provides simulated but topically-appropriate data for different research domains.
In production, these would connect to real APIs and databases.
"""

import hashlib
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class DataSourceResult:
    """Result from querying a data source."""
    source_id: str
    source_name: str
    query: str
    success: bool
    data: dict[str, Any]
    record_count: int
    data_hash: str
    latency_ms: float


# Simulated data for different topic areas
AI_SECURITY_DATA = {
    "vulnerabilities": [
        {
            "id": "CVE-2024-AI-001",
            "type": "prompt_injection",
            "severity": "high",
            "description": "Prompt injection vulnerability allows bypassing safety filters",
            "affected_systems": ["LLM chatbots", "AI assistants"],
            "mitigation": "Input sanitization and output filtering",
        },
        {
            "id": "CVE-2024-AI-002", 
            "type": "data_poisoning",
            "severity": "critical",
            "description": "Training data poisoning leads to biased or malicious outputs",
            "affected_systems": ["Fine-tuned models", "RAG systems"],
            "mitigation": "Data validation and provenance tracking",
        },
        {
            "id": "CVE-2024-AI-003",
            "type": "jailbreak",
            "severity": "high",
            "description": "Jailbreak techniques circumvent content policies",
            "affected_systems": ["All LLM-based systems"],
            "mitigation": "Multi-layer content filtering",
        },
        {
            "id": "CVE-2024-AI-004",
            "type": "model_extraction",
            "severity": "medium",
            "description": "API queries can extract model weights or behavior",
            "affected_systems": ["Hosted AI APIs"],
            "mitigation": "Rate limiting and query monitoring",
        },
        {
            "id": "CVE-2024-AI-005",
            "type": "deepfake_generation",
            "severity": "high",
            "description": "Generative AI enables creation of convincing fake media",
            "affected_systems": ["Image/video generators"],
            "mitigation": "Watermarking and detection tools",
        },
    ],
    "incidents": [
        {
            "date": "2024-03",
            "type": "phishing_automation",
            "impact": "AI-generated phishing emails increased success rate by 40%",
            "source": "Security research report",
        },
        {
            "date": "2024-05",
            "type": "code_vulnerability",
            "impact": "AI-generated code contained known vulnerabilities in 15% of cases",
            "source": "Academic study",
        },
        {
            "date": "2024-07",
            "type": "misinformation",
            "impact": "AI-generated content used in disinformation campaigns",
            "source": "Government report",
        },
    ],
    "attack_vectors": [
        "Prompt injection to extract sensitive data",
        "Adversarial inputs to bypass content filters",
        "Social engineering using AI-generated personas",
        "Automated vulnerability discovery using AI",
        "AI-powered password cracking and credential stuffing",
    ],
}

AI_BENEFITS_DATA = {
    "productivity_gains": [
        {
            "domain": "software_development",
            "metric": "coding_speed",
            "improvement": 0.55,
            "study": "GitHub Copilot productivity study 2024",
            "sample_size": 2000,
        },
        {
            "domain": "customer_service",
            "metric": "response_time",
            "improvement": 0.70,
            "study": "Enterprise AI adoption survey",
            "sample_size": 500,
        },
        {
            "domain": "content_creation",
            "metric": "output_volume",
            "improvement": 0.45,
            "study": "Marketing AI benchmark",
            "sample_size": 1200,
        },
        {
            "domain": "data_analysis",
            "metric": "analysis_speed",
            "improvement": 0.60,
            "study": "Business intelligence AI study",
            "sample_size": 800,
        },
    ],
    "cost_savings": [
        {
            "application": "automated_support",
            "savings_percent": 30,
            "implementation_cost": "medium",
        },
        {
            "application": "document_processing",
            "savings_percent": 45,
            "implementation_cost": "low",
        },
        {
            "application": "code_review",
            "savings_percent": 25,
            "implementation_cost": "low",
        },
    ],
    "quality_improvements": [
        {
            "domain": "medical_diagnosis",
            "accuracy_improvement": 0.12,
            "context": "AI-assisted radiology",
        },
        {
            "domain": "fraud_detection",
            "accuracy_improvement": 0.25,
            "context": "Financial services",
        },
        {
            "domain": "predictive_maintenance",
            "accuracy_improvement": 0.35,
            "context": "Manufacturing",
        },
    ],
}

AI_CAPABILITIES_DATA = {
    "benchmarks": [
        {
            "name": "MMLU",
            "description": "Massive Multitask Language Understanding",
            "top_score": 0.90,
            "model": "GPT-4",
            "year": 2024,
        },
        {
            "name": "HumanEval",
            "description": "Code generation benchmark",
            "top_score": 0.85,
            "model": "Claude 3.5",
            "year": 2024,
        },
        {
            "name": "MATH",
            "description": "Mathematical reasoning",
            "top_score": 0.76,
            "model": "GPT-4",
            "year": 2024,
        },
    ],
    "limitations": [
        {
            "type": "hallucination",
            "description": "Models generate plausible but factually incorrect information",
            "frequency": "common",
            "mitigation": "Retrieval augmentation, fact-checking",
        },
        {
            "type": "reasoning",
            "description": "Complex multi-step reasoning remains unreliable",
            "frequency": "moderate",
            "mitigation": "Chain-of-thought prompting, verification",
        },
        {
            "type": "temporal",
            "description": "Knowledge cutoff limits awareness of recent events",
            "frequency": "inherent",
            "mitigation": "Real-time retrieval, fine-tuning",
        },
        {
            "type": "consistency",
            "description": "Outputs vary across identical queries",
            "frequency": "common",
            "mitigation": "Temperature control, majority voting",
        },
    ],
}

ARXIV_AI_PAPERS = [
    {
        "id": "arxiv:2401.00001",
        "title": "Security Implications of Large Language Models in Enterprise Settings",
        "abstract": "This paper analyzes security vulnerabilities introduced by LLM deployment in enterprise environments, finding significant risks from prompt injection and data leakage.",
        "authors": ["Smith, J.", "Chen, L."],
        "year": 2024,
        "citations": 145,
        "topics": ["security", "LLM", "enterprise"],
    },
    {
        "id": "arxiv:2401.00002",
        "title": "Measuring Productivity Gains from AI Code Assistants",
        "abstract": "A controlled study of 5000 developers showing 40-55% improvement in coding speed with AI assistance, with quality maintained or improved.",
        "authors": ["Johnson, M.", "Patel, R."],
        "year": 2024,
        "citations": 230,
        "topics": ["productivity", "code generation", "software engineering"],
    },
    {
        "id": "arxiv:2401.00003",
        "title": "Adversarial Attacks on Generative AI: A Comprehensive Survey",
        "abstract": "Survey of 200+ attack techniques against generative AI systems, categorizing by attack surface and proposing defense frameworks.",
        "authors": ["Williams, K.", "Lee, S."],
        "year": 2024,
        "citations": 312,
        "topics": ["adversarial", "security", "attacks"],
    },
    {
        "id": "arxiv:2401.00004",
        "title": "AI-Enabled Phishing: Threat Assessment and Countermeasures",
        "abstract": "Analysis of AI-generated phishing campaigns showing 40% higher success rate. Proposes detection methods achieving 85% accuracy.",
        "authors": ["Brown, A.", "Garcia, M."],
        "year": 2024,
        "citations": 178,
        "topics": ["phishing", "security", "detection"],
    },
    {
        "id": "arxiv:2401.00005",
        "title": "Benefits and Risks of Generative AI Adoption: An Empirical Study",
        "abstract": "Survey of 500 organizations finding 65% report net positive ROI from AI adoption, while 23% report significant security incidents.",
        "authors": ["Taylor, E.", "Kim, J."],
        "year": 2024,
        "citations": 89,
        "topics": ["adoption", "ROI", "risk assessment"],
    },
]


class TopicDataSources:
    """Provides topic-relevant data for research queries."""
    
    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)
    
    def query(self, source_id: str, topic: str, context: str = "") -> DataSourceResult:
        """Query a data source for topic-relevant information."""
        start = datetime.now(timezone.utc)
        
        data, record_count = self._get_source_data(source_id, topic)
        
        latency = self.rng.uniform(50, 300)
        data_hash = hashlib.sha256(str(data).encode()).hexdigest()[:16]
        
        return DataSourceResult(
            source_id=source_id,
            source_name=self._get_source_name(source_id),
            query=f"Query {source_id} for {topic}",
            success=True,
            data=data,
            record_count=record_count,
            data_hash=data_hash,
            latency_ms=latency,
        )
    
    def _get_source_data(self, source_id: str, topic: str) -> tuple[dict, int]:
        """Get data from a specific source based on topic."""
        
        if source_id == "cve_database":
            vulns = AI_SECURITY_DATA["vulnerabilities"]
            return {
                "vulnerabilities": vulns,
                "total_count": len(vulns),
                "severity_distribution": {"critical": 1, "high": 3, "medium": 1},
            }, len(vulns)
        
        elif source_id == "security_reports":
            incidents = AI_SECURITY_DATA["incidents"]
            return {
                "incidents": incidents,
                "attack_vectors": AI_SECURITY_DATA["attack_vectors"],
            }, len(incidents)
        
        elif source_id == "arxiv_security" or source_id == "arxiv_ai":
            papers = [p for p in ARXIV_AI_PAPERS if any(
                t in ["security", "adversarial", "attacks", "phishing"] 
                for t in p["topics"]
            )] if "security" in source_id else ARXIV_AI_PAPERS
            return {
                "papers": papers,
                "total_results": len(papers),
            }, len(papers)
        
        elif source_id == "tech_reports" or source_id == "case_studies":
            return {
                "productivity_data": AI_BENEFITS_DATA["productivity_gains"],
                "cost_data": AI_BENEFITS_DATA["cost_savings"],
            }, len(AI_BENEFITS_DATA["productivity_gains"])
        
        elif source_id == "ai_benchmarks":
            return {
                "benchmarks": AI_CAPABILITIES_DATA["benchmarks"],
                "limitations": AI_CAPABILITIES_DATA["limitations"],
            }, len(AI_CAPABILITIES_DATA["benchmarks"])
        
        elif source_id == "industry_analysis" or source_id == "market_research":
            return {
                "quality_improvements": AI_BENEFITS_DATA["quality_improvements"],
                "adoption_metrics": {
                    "enterprise_adoption_rate": 0.45,
                    "yoy_growth": 0.35,
                    "top_use_cases": ["customer_service", "code_generation", "data_analysis"],
                },
            }, 5
        
        else:
            # Default fallback
            return {
                "message": f"Data for {source_id} on {topic}",
                "records": [],
            }, 0
    
    def _get_source_name(self, source_id: str) -> str:
        """Get human-readable source name."""
        names = {
            "cve_database": "CVE Security Database",
            "security_reports": "Security Incident Reports",
            "arxiv_security": "arXiv Security Papers",
            "arxiv_ai": "arXiv AI Research",
            "tech_reports": "Technology Research Reports",
            "case_studies": "Enterprise Case Studies",
            "ai_benchmarks": "AI Benchmark Database",
            "industry_analysis": "Industry Analysis Reports",
            "market_research": "Market Research Data",
            "policy_reports": "Policy & Regulatory Reports",
            "academic_papers": "Academic Research Papers",
        }
        return names.get(source_id, source_id.replace("_", " ").title())
    
    def query_multiple(
        self, 
        sources: list[dict], 
        topic: str,
    ) -> list[DataSourceResult]:
        """Query multiple data sources."""
        results = []
        for source in sources:
            result = self.query(source["source_id"], topic)
            results.append(result)
        return results
