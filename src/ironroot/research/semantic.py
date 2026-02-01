# Author: Bradley R. Kinnard
"""Semantic Research Parser - Extracts topics and generates relevant research.

This module parses user criteria to:
1. Extract topics, keywords, and intent
2. Map to relevant research domains
3. Generate contextually appropriate questions
4. Select relevant data sources
"""

import re
from dataclasses import dataclass, field
from enum import Enum


class ResearchIntent(str, Enum):
    """Primary intent of the research request."""
    COMPARISON = "comparison"  # X vs Y, pros/cons
    CAUSATION = "causation"    # Does X cause Y
    MEASUREMENT = "measurement"  # How much, what level
    PREDICTION = "prediction"  # Will X happen
    EXPLORATION = "exploration"  # General understanding
    EVALUATION = "evaluation"  # Is X good/bad


@dataclass
class TopicExtraction:
    """Extracted topics from user criteria."""
    primary_topics: list[str]
    secondary_topics: list[str]
    keywords: list[str]
    intent: ResearchIntent
    sentiment_targets: list[str]  # Things being evaluated (risk/benefit)
    domain_hints: list[str]


@dataclass
class ResearchDomain:
    """A research domain with relevant sources and question templates."""
    name: str
    keywords: list[str]
    question_templates: list[str]
    hypothesis_templates: list[str]
    data_sources: list[str]
    metrics: list[str]


# Topic keyword mappings
TOPIC_KEYWORDS = {
    "artificial_intelligence": [
        "ai", "artificial intelligence", "machine learning", "ml", "deep learning",
        "neural network", "llm", "large language model", "gpt", "chatgpt", "claude",
        "generative ai", "genai", "transformer", "nlp", "natural language",
        "computer vision", "robotics", "automation", "algorithm",
        "reinforcement learning", "reinforced learning", "rl", "supervised learning",
        "unsupervised learning", "training", "model", "inference", "fine-tuning",
        "accuracy", "precision", "recall", "f1", "benchmark", "performance",
        "classification", "regression", "prediction", "neural", "network",
        "gradient", "backpropagation", "optimization", "loss function"
    ],
    "cybersecurity": [
        "security", "cybersecurity", "cyber", "hack", "hacking", "vulnerability",
        "exploit", "malware", "ransomware", "phishing", "attack", "threat",
        "breach", "data breach", "privacy", "encryption", "authentication",
        "firewall", "intrusion", "risk", "cve", "zero-day"
    ],
    "technology": [
        "technology", "tech", "software", "hardware", "computer", "digital",
        "internet", "cloud", "saas", "platform", "system", "infrastructure",
        "data", "database", "api", "code", "programming", "development"
    ],
    "business": [
        "business", "company", "enterprise", "corporate", "industry", "market",
        "revenue", "profit", "cost", "roi", "productivity", "efficiency",
        "workforce", "employment", "job", "labor", "economy", "economic"
    ],
    "healthcare": [
        "health", "healthcare", "medical", "medicine", "clinical", "patient",
        "diagnosis", "treatment", "drug", "pharmaceutical", "hospital", "doctor"
    ],
    "finance": [
        "finance", "financial", "bank", "banking", "investment", "stock",
        "trading", "cryptocurrency", "crypto", "bitcoin", "fraud", "money"
    ],
    "education": [
        "education", "school", "university", "student", "teaching",
        "academic", "curriculum", "classroom", "teacher", "pedagogy"
    ],
    "environment": [
        "climate", "environment", "environmental", "sustainability", "carbon",
        "emissions", "pollution", "renewable", "energy", "green"
    ],
    "society": [
        "society", "social", "culture", "ethics", "ethical", "bias", "fairness",
        "discrimination", "human", "rights", "regulation", "policy", "law", "legal"
    ],
}

# Intent detection patterns
INTENT_PATTERNS = {
    ResearchIntent.COMPARISON: [
        r"\bvs\b", r"\bversus\b", r"\bcompare\b", r"\bcomparison\b",
        r"\bor\b.*\b(benefit|risk|advantage|disadvantage)\b",
        r"\b(risk|benefit)\b.*\bor\b",
        r"\bpros?\s*(and|&)\s*cons?\b",
        r"\b(better|worse)\b.*\bthan\b",
    ],
    ResearchIntent.CAUSATION: [
        r"\bcause[sd]?\b", r"\blead[s]?\s*to\b", r"\bresult[s]?\s*in\b",
        r"\beffect[s]?\s*(of|on)\b", r"\bimpact[s]?\s*(of|on)\b",
        r"\binfluence[s]?\b", r"\bdoes\b.*\b(affect|change|improve)\b",
    ],
    ResearchIntent.MEASUREMENT: [
        r"\bhow\s+(much|many|often|long)\b", r"\bwhat\s+(level|amount|rate)\b",
        r"\bmeasure\b", r"\bquantify\b", r"\bstatistics?\b",
    ],
    ResearchIntent.PREDICTION: [
        r"\bwill\b", r"\bfuture\b", r"\bpredict\b", r"\bforecast\b",
        r"\btrend\b", r"\bexpect\b", r"\banticipate\b",
    ],
    ResearchIntent.EVALUATION: [
        r"\b(good|bad)\b", r"\b(risk|benefit|advantage|disadvantage)\b",
        r"\b(safe|dangerous|harmful|helpful)\b", r"\bshould\b",
        r"\b(worth|value)\b", r"\bevaluate\b", r"\bassess\b",
    ],
}

# Domain definitions with contextual question templates
RESEARCH_DOMAINS = {
    "ai_capabilities": ResearchDomain(
        name="AI Capabilities & Limitations",
        keywords=["ai", "capabilities", "performance", "accuracy", "limitation"],
        question_templates=[
            "What are the documented capabilities of {topic} systems?",
            "What are the known limitations of {topic} technology?",
            "How does {topic} performance compare across different use cases?",
            "What benchmarks exist for evaluating {topic}?",
        ],
        hypothesis_templates=[
            "{topic} demonstrates measurable improvements in {metric}",
            "{topic} has documented limitations in {context}",
            "Performance of {topic} varies significantly by application domain",
        ],
        data_sources=["arxiv_ai", "ai_benchmarks", "tech_reports"],
        metrics=["accuracy", "performance_score", "benchmark_result", "error_rate"],
    ),
    "ai_security": ResearchDomain(
        name="AI Security & Risks",
        keywords=["security", "risk", "vulnerability", "attack", "adversarial"],
        question_templates=[
            "What security vulnerabilities have been identified in {topic} systems?",
            "What attack vectors exist for {topic} technology?",
            "How can {topic} be exploited for malicious purposes?",
            "What security incidents involving {topic} have been documented?",
        ],
        hypothesis_templates=[
            "{topic} introduces new security vulnerabilities",
            "{topic} can be exploited for {attack_type} attacks",
            "Security risks from {topic} outweigh benefits in {context}",
            "{topic} creates novel attack surfaces not present in traditional systems",
        ],
        data_sources=["cve_database", "security_reports", "arxiv_security"],
        metrics=["vulnerability_count", "incident_rate", "attack_success_rate", "risk_score"],
    ),
    "ai_benefits": ResearchDomain(
        name="AI Benefits & Opportunities",
        keywords=["benefit", "advantage", "improvement", "efficiency", "automation"],
        question_templates=[
            "What measurable benefits does {topic} provide?",
            "How does {topic} improve efficiency or productivity?",
            "What positive outcomes have been documented from {topic} adoption?",
            "What problems does {topic} solve better than alternatives?",
        ],
        hypothesis_templates=[
            "{topic} provides measurable benefits in {context}",
            "Adoption of {topic} leads to improved {metric}",
            "Benefits of {topic} outweigh risks in {context}",
            "{topic} enables capabilities not possible with traditional approaches",
        ],
        data_sources=["tech_reports", "case_studies", "industry_analysis"],
        metrics=["efficiency_gain", "cost_reduction", "time_savings", "quality_improvement"],
    ),
    "ai_ethics": ResearchDomain(
        name="AI Ethics & Society",
        keywords=["ethics", "bias", "fairness", "society", "regulation", "policy"],
        question_templates=[
            "What ethical concerns have been raised about {topic}?",
            "How does {topic} impact different demographic groups?",
            "What regulatory frameworks exist for {topic}?",
            "What societal changes result from widespread {topic} adoption?",
        ],
        hypothesis_templates=[
            "{topic} exhibits measurable bias in {context}",
            "Regulation of {topic} reduces negative societal impacts",
            "Ethical guidelines improve {topic} outcomes",
        ],
        data_sources=["policy_reports", "academic_papers", "regulatory_filings"],
        metrics=["bias_score", "fairness_metric", "compliance_rate", "public_sentiment"],
    ),
    "technology_adoption": ResearchDomain(
        name="Technology Adoption & Trends",
        keywords=["adoption", "trend", "market", "growth", "enterprise"],
        question_templates=[
            "What is the current adoption rate of {topic}?",
            "How has {topic} adoption changed over time?",
            "What factors drive or hinder {topic} adoption?",
            "Which industries lead in {topic} adoption?",
        ],
        hypothesis_templates=[
            "{topic} adoption is accelerating in {context}",
            "Enterprise adoption of {topic} lags consumer adoption",
            "Regulatory uncertainty slows {topic} adoption",
        ],
        data_sources=["market_research", "industry_surveys", "tech_reports"],
        metrics=["adoption_rate", "market_share", "growth_rate", "penetration"],
    ),
    "ml_performance": ResearchDomain(
        name="ML Model Performance & Accuracy",
        keywords=["accuracy", "performance", "learning", "training", "model", "benchmark"],
        question_templates=[
            "How does {topic} affect model accuracy compared to baselines?",
            "What performance benchmarks exist for {topic}?",
            "Under what conditions does {topic} improve or degrade performance?",
            "What are the trade-offs between {topic} and other approaches?",
        ],
        hypothesis_templates=[
            "{topic} improves accuracy over baseline methods",
            "{topic} shows diminishing returns at scale",
            "Performance gains from {topic} are task-dependent",
            "{topic} outperforms alternatives on {metric}",
        ],
        data_sources=["arxiv_ai", "ai_benchmarks", "ml_papers"],
        metrics=["accuracy", "f1_score", "precision", "recall", "loss", "benchmark_score"],
    ),
}


def extract_topics(criteria: str) -> TopicExtraction:
    """Extract topics, keywords, and intent from research criteria.

    Parses natural language criteria to identify:
    - Primary topics (main subject areas)
    - Secondary topics (related areas)
    - Keywords for search
    - Research intent
    - Things being evaluated
    """
    criteria_lower = criteria.lower()

    # Find matching topics
    topic_scores: dict[str, int] = {}
    matched_keywords: list[str] = []

    for topic, keywords in TOPIC_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            if keyword in criteria_lower:
                score += 1
                if keyword not in matched_keywords:
                    matched_keywords.append(keyword)
        if score > 0:
            topic_scores[topic] = score

    # Sort by score
    sorted_topics = sorted(topic_scores.items(), key=lambda x: x[1], reverse=True)

    primary = [t[0] for t in sorted_topics[:2]] if sorted_topics else ["technology"]
    secondary = [t[0] for t in sorted_topics[2:4]] if len(sorted_topics) > 2 else []

    # Detect intent
    intent = _detect_intent(criteria_lower)

    # Extract sentiment targets (risk/benefit evaluation)
    sentiment_targets = _extract_sentiment_targets(criteria_lower)

    # Map to research domains (pass keywords for performance detection)
    domain_hints = _map_to_domains(primary, secondary, intent, sentiment_targets, matched_keywords)

    return TopicExtraction(
        primary_topics=primary,
        secondary_topics=secondary,
        keywords=matched_keywords,
        intent=intent,
        sentiment_targets=sentiment_targets,
        domain_hints=domain_hints,
    )


def _detect_intent(text: str) -> ResearchIntent:
    """Detect the primary research intent."""
    for intent, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return intent
    return ResearchIntent.EXPLORATION


def _extract_sentiment_targets(text: str) -> list[str]:
    """Extract things being evaluated (risk, benefit, etc.)."""
    targets = []

    sentiment_words = [
        "risk", "benefit", "advantage", "disadvantage", "danger", "safety",
        "threat", "opportunity", "harm", "help", "good", "bad", "positive", "negative"
    ]

    for word in sentiment_words:
        if word in text:
            targets.append(word)

    return targets


def _map_to_domains(
    primary: list[str],
    secondary: list[str],
    intent: ResearchIntent,
    sentiment_targets: list[str],
    keywords: list[str] | None = None,
) -> list[str]:
    """Map extracted topics to research domains."""
    domains = []
    keywords = keywords or []

    # Check for AI + security/risk combination
    has_ai = "artificial_intelligence" in primary or "artificial_intelligence" in secondary
    has_security = "cybersecurity" in primary or "cybersecurity" in secondary
    has_risk = any(t in sentiment_targets for t in ["risk", "danger", "threat", "harm"])
    has_benefit = any(t in sentiment_targets for t in ["benefit", "advantage", "opportunity", "help"])

    # Check for ML performance keywords
    performance_keywords = ["accuracy", "performance", "learning", "training", "benchmark", "model"]
    has_performance = any(kw in keywords for kw in performance_keywords)

    if has_ai:
        domains.append("ai_capabilities")

        # Add ML performance domain for accuracy/performance questions
        if has_performance or intent == ResearchIntent.MEASUREMENT:
            domains.append("ml_performance")

        if has_security or has_risk:
            domains.append("ai_security")

        if has_benefit:
            domains.append("ai_benefits")

        if intent == ResearchIntent.EVALUATION:
            if "ai_security" not in domains:
                domains.append("ai_security")
            if "ai_benefits" not in domains:
                domains.append("ai_benefits")

        # For causation intent (does X affect Y), add ML performance
        if intent == ResearchIntent.CAUSATION and "ml_performance" not in domains:
            domains.append("ml_performance")

    # Add ethics if relevant keywords found
    if any(t in primary + secondary for t in ["society"]):
        domains.append("ai_ethics")

    # Add technology adoption for business context
    if "business" in primary or "technology" in primary:
        domains.append("technology_adoption")

    # Default fallback - if we have AI but no domains, add capabilities and performance
    if not domains and has_ai:
        domains = ["ai_capabilities", "ml_performance"]
    elif not domains:
        domains = ["ai_capabilities", "ml_performance"]

    return domains


def get_domain(name: str) -> ResearchDomain | None:
    """Get a research domain by name."""
    return RESEARCH_DOMAINS.get(name)


def generate_questions(extraction: TopicExtraction, max_questions: int = 5) -> list[dict]:
    """Generate relevant research questions based on extracted topics."""
    questions = []
    topic_label = " ".join(extraction.keywords[:3]) if extraction.keywords else "this technology"

    for domain_name in extraction.domain_hints[:3]:
        domain = RESEARCH_DOMAINS.get(domain_name)
        if not domain:
            continue

        for template in domain.question_templates[:2]:
            question_text = template.format(
                topic=topic_label,
                metric=domain.metrics[0] if domain.metrics else "performance",
                context="enterprise settings",
            )

            questions.append({
                "domain": domain.name,
                "text": question_text,
                "template_source": domain_name,
                "relevance_score": 0.85,
            })

            if len(questions) >= max_questions:
                break

        if len(questions) >= max_questions:
            break

    return questions


def generate_hypotheses(
    extraction: TopicExtraction,
    questions: list[dict],
    max_hypotheses: int = 10,
) -> list[dict]:
    """Generate relevant hypotheses based on topics and questions."""
    hypotheses = []
    topic_label = " ".join(extraction.keywords[:3]) if extraction.keywords else "this technology"

    # Generate based on intent
    if extraction.intent == ResearchIntent.COMPARISON or extraction.intent == ResearchIntent.EVALUATION:
        # Both positive and negative hypotheses
        for domain_name in extraction.domain_hints[:3]:
            domain = RESEARCH_DOMAINS.get(domain_name)
            if not domain:
                continue

            for template in domain.hypothesis_templates[:2]:
                hypothesis_text = template.format(
                    topic=topic_label,
                    metric=domain.metrics[0] if domain.metrics else "outcomes",
                    context="real-world applications",
                    attack_type="prompt injection" if "security" in domain_name else "misuse",
                )

                hypotheses.append({
                    "statement": hypothesis_text,
                    "domain": domain.name,
                    "testable": True,
                    "prior_probability": 0.5,
                })

                if len(hypotheses) >= max_hypotheses:
                    break

            if len(hypotheses) >= max_hypotheses:
                break

    # Add null hypothesis
    if len(hypotheses) < max_hypotheses:
        hypotheses.append({
            "statement": f"There is no significant difference in outcomes with vs without {topic_label}",
            "domain": "null_hypothesis",
            "testable": True,
            "prior_probability": 0.3,
        })

    return hypotheses


def get_relevant_data_sources(extraction: TopicExtraction) -> list[dict]:
    """Get data sources relevant to the extracted topics."""
    sources = []
    seen = set()

    for domain_name in extraction.domain_hints:
        domain = RESEARCH_DOMAINS.get(domain_name)
        if not domain:
            continue

        for source in domain.data_sources:
            if source not in seen:
                seen.add(source)
                sources.append({
                    "source_id": source,
                    "domain": domain.name,
                    "relevance": "high",
                })

    return sources
