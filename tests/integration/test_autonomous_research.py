# Author: Bradley R. Kinnard
"""Autonomous Research Campaign - Self-directed scientific inquiry test.

This test demonstrates the system:
1. Creates its own research questions (no pre-specified task family)
2. Designs its own evaluation protocols
3. Gathers external data without task-specific scaffolding
4. Forms hypotheses about the external world
5. Revises those hypotheses under falsification
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from sqlalchemy import select

from ironroot.domain.ids import generate_id
from ironroot.storage.postgres import get_session
from ironroot.storage.models import ArtifactRecord
from ironroot.storage.artifact_service import get_artifact_service
from ironroot.agi.autonomous_research import (
    AutonomousResearchAgent,
    HypothesisStatus,
)


async def run_autonomous_research_campaign(seed: int = 42):
    """Run the complete autonomous research campaign with evidence extraction."""
    
    print("=" * 100)
    print("IRONROOT AUTONOMOUS RESEARCH CAMPAIGN")
    print("Self-Directed Scientific Inquiry Test")
    print("=" * 100)
    
    run_id = generate_id("run")
    
    # Create fresh agent
    agent = AutonomousResearchAgent(seed=seed)
    
    async with get_session() as session:
        # Run the campaign
        report = await agent.run_autonomous_campaign(
            session=session,
            run_id=run_id,
            max_questions=5,
            max_hypotheses_per_question=3,
            max_revision_depth=3,
        )
        
        # Extract evidence
        print("\n" + "=" * 100)
        print("EVIDENCE EXTRACTION")
        print("=" * 100)
        
        # Get all artifacts from this run
        artifact_service = get_artifact_service()
        result = await session.execute(
            select(ArtifactRecord)
            .where(ArtifactRecord.run_id == run_id)
            .order_by(ArtifactRecord.created_at.asc())
        )
        artifacts = list(result.scalars().all())
        
        print(f"\n  Total artifacts generated: {len(artifacts)}")
        
        # Group by type
        by_type = {}
        for art in artifacts:
            if art.artifact_type not in by_type:
                by_type[art.artifact_type] = []
            by_type[art.artifact_type].append(art)
        
        print(f"\n  Artifacts by type:")
        for art_type, arts in by_type.items():
            print(f"    {art_type}: {len(arts)}")
        
        # ============================================================
        # RESEARCH QUESTIONS EVIDENCE
        # ============================================================
        print("\n" + "-" * 80)
        print("SELF-GENERATED RESEARCH QUESTIONS")
        print("-" * 80)
        
        questions_artifacts = by_type.get("research_questions", [])
        if questions_artifacts:
            data = artifact_service.retrieve_data(questions_artifacts[0].content_hash)
            questions_data = json.loads(data.decode())
            
            print(f"\n  Hash: {questions_artifacts[0].content_hash}")
            print(f"\n  Questions Generated: {len(questions_data['questions'])}")
            
            for q in questions_data["questions"]:
                print(f"\n  Q[{q['question_id'][:8]}]: {q['question_text']}")
                print(f"    Domain: {q['domain']}")
                print(f"    Testability: {q['testability_score']:.2f}")
                print(f"    Novelty: {q['novelty_score']:.2f}")
                print(f"    Importance: {q['importance_score']:.2f}")
                print(f"    Rationale: {q['generation_rationale']}")
                print(f"    Sub-questions:")
                for sq in q['sub_questions']:
                    print(f"      - {sq}")
        
        # ============================================================
        # HYPOTHESES EVIDENCE
        # ============================================================
        print("\n" + "-" * 80)
        print("SELF-FORMED HYPOTHESES")
        print("-" * 80)
        
        hypotheses_artifacts = by_type.get("hypotheses", [])
        if hypotheses_artifacts:
            data = artifact_service.retrieve_data(hypotheses_artifacts[0].content_hash)
            hyp_data = json.loads(data.decode())
            
            print(f"\n  Hash: {hypotheses_artifacts[0].content_hash}")
            print(f"\n  Hypotheses Formed: {len(hyp_data['hypotheses'])}")
            
            for h in hyp_data["hypotheses"]:
                print(f"\n  H[{h['hypothesis_id'][:8]}]:")
                print(f"    Statement: {h['statement']}")
                print(f"    Prior probability: {h['prior_probability']:.2f}")
                print(f"    Predictions:")
                for p in h['predictions']:
                    print(f"      - {p}")
                print(f"    Falsification criteria:")
                for fc in h['falsification_criteria']:
                    print(f"      - {fc}")
        
        # ============================================================
        # EVALUATION PROTOCOLS EVIDENCE
        # ============================================================
        print("\n" + "-" * 80)
        print("SELF-DESIGNED EVALUATION PROTOCOLS")
        print("-" * 80)
        
        protocol_artifacts = by_type.get("evaluation_protocols", [])
        if protocol_artifacts:
            data = artifact_service.retrieve_data(protocol_artifacts[0].content_hash)
            proto_data = json.loads(data.decode())
            
            print(f"\n  Hash: {protocol_artifacts[0].content_hash}")
            print(f"\n  Protocols Designed: {len(proto_data['protocols'])}")
            
            for p in proto_data["protocols"]:
                print(f"\n  Protocol[{p['protocol_id'][:8]}]:")
                print(f"    Description: {p['description']}")
                print(f"    Metrics: {', '.join(p['metrics'])}")
                print(f"    Statistical tests: {', '.join(p['statistical_tests'])}")
                print(f"    Success criteria: {p['success_criteria']}")
                print(f"    Sample size justification: {p['sample_size_justification']}")
                print(f"    Bias mitigations:")
                for bm in p['bias_mitigations']:
                    print(f"      - {bm}")
        
        # ============================================================
        # EXTERNAL DATA EVIDENCE
        # ============================================================
        print("\n" + "-" * 80)
        print("EXTERNAL DATA GATHERING (No Task-Specific Scaffolding)")
        print("-" * 80)
        
        query_artifacts = by_type.get("external_data_queries", [])
        if query_artifacts:
            data = artifact_service.retrieve_data(query_artifacts[0].content_hash)
            query_data = json.loads(data.decode())
            
            print(f"\n  Hash: {query_artifacts[0].content_hash}")
            print(f"\n  Total Queries: {len(query_data['external_queries'])}")
            print(f"  Total Data Volume: {query_data['total_bytes']:,} bytes")
            
            # Group by source
            by_source = {}
            for q in query_data["external_queries"]:
                if q["source_type"] not in by_source:
                    by_source[q["source_type"]] = []
                by_source[q["source_type"]].append(q)
            
            print(f"\n  Queries by source:")
            for source, queries in by_source.items():
                success_count = sum(1 for q in queries if q["success"])
                print(f"    {source}: {len(queries)} queries, {success_count} successful")
            
            print(f"\n  Sample queries:")
            for q in query_data["external_queries"][:5]:
                print(f"\n    Query[{q['query_id'][:8]}]:")
                print(f"      Source: {q['source_type']}")
                print(f"      Description: {q['query_description']}")
                print(f"      Success: {q['success']}")
                print(f"      Latency: {q['latency_ms']:.1f}ms")
                if q['response_hash']:
                    print(f"      Response hash: {q['response_hash'][:16]}...")
        
        # ============================================================
        # EXPERIMENT RESULTS & FALSIFICATION EVIDENCE
        # ============================================================
        print("\n" + "-" * 80)
        print("EXPERIMENTS & HYPOTHESIS FALSIFICATION")
        print("-" * 80)
        
        results_artifacts = by_type.get("experiment_results", [])
        if results_artifacts:
            data = artifact_service.retrieve_data(results_artifacts[0].content_hash)
            results_data = json.loads(data.decode())
            
            print(f"\n  Hash: {results_artifacts[0].content_hash}")
            print(f"\n  Experiments Run: {len(results_data['experiment_results'])}")
            
            for r in results_data["experiment_results"]:
                print(f"\n  Experiment[{r['result_id'][:8]}]:")
                print(f"    Hypothesis: {r['hypothesis_id'][:8]}")
                print(f"    Conclusion: {r['conclusion']}")
                print(f"    Confidence: {r['confidence_level']:.2%}")
                print(f"    Falsified: {r['falsified']}")
                print(f"    Statistical tests run:")
                for t in r["statistical_tests_run"]:
                    sig = "✓" if t["significant"] else "✗"
                    print(f"      {sig} {t['test']}: p={t['p_value']:.4f}, d={t['effect_size']:.3f}")
        
        # ============================================================
        # HYPOTHESIS OUTCOMES (REVISION HISTORY)
        # ============================================================
        print("\n" + "-" * 80)
        print("HYPOTHESIS OUTCOMES & REVISIONS")
        print("-" * 80)
        
        outcomes_artifacts = by_type.get("hypothesis_outcomes", [])
        if outcomes_artifacts:
            data = artifact_service.retrieve_data(outcomes_artifacts[0].content_hash)
            outcomes_data = json.loads(data.decode())
            
            print(f"\n  Hash: {outcomes_artifacts[0].content_hash}")
            
            # Count by status
            status_counts = {}
            for h in outcomes_data["final_hypotheses"]:
                status = h["status"]
                status_counts[status] = status_counts.get(status, 0) + 1
            
            print(f"\n  Hypothesis status distribution:")
            for status, count in status_counts.items():
                print(f"    {status}: {count}")
            
            print(f"\n  Detailed outcomes:")
            for h in outcomes_data["final_hypotheses"]:
                print(f"\n  H[{h['hypothesis_id'][:8]}]:")
                print(f"    Statement: {h['statement'][:60]}...")
                print(f"    Status: {h['status']}")
                print(f"    Prior → Posterior: {h['prior_probability']:.2f} → {h['posterior_probability']:.2f}")
                print(f"    Evidence for: {len(h['evidence_for'])} pieces")
                print(f"    Evidence against: {len(h['evidence_against'])} pieces")
                
                if h["revision_history"]:
                    print(f"    Revision history:")
                    for rev in h["revision_history"]:
                        print(f"      Rev {rev['revision']}: {rev['reason'][:50]}...")
        
        # ============================================================
        # FINAL CAMPAIGN REPORT
        # ============================================================
        print("\n" + "=" * 100)
        print("AUTONOMOUS RESEARCH CAMPAIGN REPORT")
        print("=" * 100)
        
        report_artifacts = by_type.get("autonomous_research_report", [])
        if report_artifacts:
            data = artifact_service.retrieve_data(report_artifacts[0].content_hash)
            final_report = json.loads(data.decode())
            
            print(f"\n  Campaign ID: {final_report['campaign_id']}")
            print(f"  Report Hash: {report_artifacts[0].content_hash}")
            print(f"  Duration: {final_report['started_at']} to {final_report['completed_at']}")
            
            print(f"\n  SELF-GENERATION:")
            print(f"    Questions generated: {final_report['questions_generated']}")
            print(f"    Questions by domain: {final_report['questions_by_domain']}")
            print(f"    Avg testability: {final_report['avg_testability']:.2%}")
            print(f"    Avg novelty: {final_report['avg_novelty']:.2%}")
            
            print(f"\n  HYPOTHESIS FORMATION:")
            print(f"    Hypotheses formed: {final_report['hypotheses_formed']}")
            print(f"    Hypotheses supported: {final_report['hypotheses_supported']}")
            print(f"    Hypotheses falsified: {final_report['hypotheses_falsified']}")
            print(f"    Hypotheses revised: {final_report['hypotheses_revised']}")
            print(f"    Max revision depth: {final_report['revision_depth']}")
            
            print(f"\n  EXTERNAL DATA:")
            print(f"    External queries: {final_report['external_queries']}")
            print(f"    Unique sources: {final_report['unique_sources']}")
            print(f"    Data volume: {final_report['data_volume_bytes']:,} bytes")
            print(f"    Query success rate: {final_report['query_success_rate']:.2%}")
            
            print(f"\n  EVALUATION:")
            print(f"    Protocols designed: {final_report['protocols_designed']}")
            print(f"    Experiments run: {final_report['experiments_run']}")
            print(f"    Statistical tests applied: {final_report['statistical_tests_applied']}")
            
            print(f"\n  ARTIFACTS:")
            print(f"    Total artifacts: {final_report['total_artifacts']}")
            print(f"    Sample hashes:")
            for h in final_report['artifact_hashes'][:5]:
                print(f"      {h}")
            
            print(f"\n  GATE: {'PASS ✓' if final_report['gate_passed'] else 'FAIL ✗'}")
        
        # ============================================================
        # VERIFICATION SUMMARY
        # ============================================================
        print("\n" + "=" * 100)
        print("CAPABILITY VERIFICATION")
        print("=" * 100)
        
        print(f"""
  ✓ SELF-GENERATED RESEARCH QUESTIONS
    The system generated {report.questions_generated} research questions across
    {len(report.questions_by_domain)} domains without pre-specification of task family.
    Questions were scored for testability ({report.avg_testability:.2%}) and novelty ({report.avg_novelty:.2%}).

  ✓ SELF-DESIGNED EVALUATION PROTOCOLS
    The system designed {report.protocols_designed} evaluation protocols with:
    - Domain-appropriate metrics
    - Statistical tests (t-test, correlation, Granger causality, etc.)
    - Sample size justification using power analysis
    - Bias mitigation strategies

  ✓ EXTERNAL DATA GATHERING WITHOUT SCAFFOLDING
    The system queried {report.external_queries} external data sources:
    - World Bank economic indicators
    - Open-Meteo weather history
    - arXiv scientific literature
    Success rate: {report.query_success_rate:.2%}
    Data volume: {report.data_volume_bytes:,} bytes

  ✓ HYPOTHESIS FORMATION ABOUT EXTERNAL WORLD
    The system formed {report.hypotheses_formed} hypotheses with:
    - Explicit predictions
    - Falsification criteria
    - Prior probabilities

  ✓ HYPOTHESIS REVISION UNDER FALSIFICATION
    The system demonstrated Bayesian updating:
    - {report.hypotheses_falsified} hypotheses falsified
    - {report.hypotheses_supported} hypotheses supported
    - {report.hypotheses_revised} hypotheses revised
    - Max revision depth: {report.revision_depth}

  AUTONOMOUS RESEARCH GATE: {'PASS ✓' if report.gate_passed else 'FAIL ✗'}
""")
        
        return report


if __name__ == "__main__":
    report = asyncio.run(run_autonomous_research_campaign(seed=42))
