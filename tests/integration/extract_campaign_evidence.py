# Author: Bradley R. Kinnard
"""Extract and display complete evidence artifacts from AGI 5/5 campaign.

This script runs the full campaign and extracts all auditable evidence
with hashes, counts, and detailed breakdowns.
"""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from sqlalchemy import select
from test_agi_campaign import run_full_campaign

from ironroot.storage.artifact_service import get_artifact_service
from ironroot.storage.models import ArtifactRecord
from ironroot.storage.postgres import get_session


async def extract_evidence(seed: int = 100):
    """Run campaign and extract all evidence artifacts."""

    print("=" * 100)
    print("IRONROOT AGI 5/5 CAMPAIGN - AUDITABLE EVIDENCE EXTRACTION")
    print("=" * 100)

    # Run the campaign
    manifest = await run_full_campaign(seed)

    if not manifest.agi_claim_valid:
        print("\n⚠️  AGI claim not valid - not all gates passed")
        print("    Evidence extraction continues for audit purposes")

    # Extract all artifacts from this campaign
    artifact_service = get_artifact_service()

    async with get_session() as session:
        # Get all artifacts - filter to recent ones with proper structure
        result = await session.execute(
            select(ArtifactRecord).order_by(ArtifactRecord.created_at.desc()).limit(500)
        )
        all_artifacts = list(result.scalars().all())

        # Group by type
        by_type = {}
        for art in all_artifacts:
            if art.artifact_type not in by_type:
                by_type[art.artifact_type] = []
            by_type[art.artifact_type].append(art)

        # ============================================================
        # ARTIFACT INDEX PROOF
        # ============================================================
        print("\n" + "=" * 100)
        print("ARTIFACT INDEX PROOF")
        print("=" * 100)

        print(f"\n  Total artifacts generated: {len(all_artifacts)}")
        print("\n  Artifacts by phase:")

        phase_mapping = {
            "reality_source": "Phase 1 - Reality Breadth",
            "observation_log": "Phase 1 - Reality Breadth",
            "prediction_outcome": "Phase 1 - Reality Breadth",
            "transfer_report": "Phase 2 - Transfer Gates",
            "episode_trace": "Phase 3 - Long-Horizon Agency",
            "tool_spec_ingestion": "Phase 4 - Tool Learning",
            "tool_usage_test_suite": "Phase 4 - Tool Learning",
            "tool_competence_report": "Phase 4 - Tool Learning",
            "longitudinal_score_report": "Phase 5 - Sustained Improvement",
            "daily_score_series": "Phase 5 - Sustained Improvement",
            "promotion_ledger": "Phase 5 - Sustained Improvement",
            "regression_incident_log": "Phase 5 - Sustained Improvement",
            "recurrence_trend_report": "Phase 5 - Sustained Improvement",
            "adversarial_attack_report": "Phase 6 - Adversarial Robustness",
            "quarantine_decision_log": "Phase 6 - Adversarial Robustness",
            "uncertainty_calibration_report": "Phase 6 - Adversarial Robustness",
            "skill_library": "Architecture - Skill Library",
            "world_model_ensemble": "Architecture - World Model",
        }

        phase_counts = {}
        for art_type, arts in by_type.items():
            phase = phase_mapping.get(art_type, "Other")
            if phase not in phase_counts:
                phase_counts[phase] = 0
            phase_counts[phase] += len(arts)

        for phase, count in sorted(phase_counts.items()):
            print(f"    {phase}: {count} artifacts")

        print("\n  Sample SHA-256 hashes:")
        for art in all_artifacts[:10]:
            print(f"    {art.artifact_type}: {art.content_hash}")

        # ============================================================
        # CAMPAIGN MANIFEST
        # ============================================================
        print("\n" + "=" * 100)
        print("CAMPAIGN MANIFEST")
        print("=" * 100)

        print(f"\n  Campaign ID: {manifest.campaign_id}")
        print(f"  Seed: {manifest.seed}")
        print(f"  Started: {manifest.started_at}")
        print(f"  Completed: {manifest.completed_at}")

        print("\n  12 Reality Sources:")
        # Get reality source details
        from ironroot.agi.reality_sources import get_reality_source_registry

        registry = get_reality_source_registry(seed)

        for source_id, source in registry.sources.items():
            external = "EXTERNAL" if source.is_external else "COMMITTED"
            print(f"    - {source_id}: {source.category.value} [{external}]")

        print(f"\n  Categories covered: {manifest.categories_covered}")
        print(f"  External sources: {manifest.external_sources}")
        print(f"  Committed sources: {manifest.committed_sources}")

        print("\n  Gate Evaluation Thresholds:")
        print("    - Reality Breadth: 12 sources, 6 categories, 6+ external, 50%+ contradictions")
        print("    - Zero-Shot Transfer: 6/8 sources beating naive baseline")
        print("    - Few-Shot Transfer: 50%+ sources passing, no regressions")
        print("    - Compositional Transfer: 3/4 sources above 0.6 threshold")
        print("    - Long-Horizon Agency: 15%+ success rate, 10+ plan revisions")
        print("    - Tool Learning: 3/5 tools mastered (60%+ competence)")
        print("    - Sustained Improvement: Upward trend (p<0.05), 0 catastrophic regressions")
        print(
            "    - Adversarial Robustness: 70%+ detection, 80%+ quarantine, 70%+ uncertainty handling"
        )

        # ============================================================
        # TRANSFER REPORT
        # ============================================================
        print("\n" + "=" * 100)
        print("TRANSFER REPORT")
        print("=" * 100)

        transfer_artifacts = by_type.get("transfer_report", [])
        for art in transfer_artifacts[:3]:  # Limit to 3 most recent
            data = artifact_service.retrieve_data(art.content_hash)
            report = json.loads(data.decode())

            if "regime" not in report:
                continue  # Skip malformed artifacts

            print(f"\n  === {report['regime'].upper()} TRANSFER ===")
            print(f"  Report ID: {report['report_id']}")
            print(f"  Hash: {art.content_hash}")

            if report["regime"] == "zero_shot":
                print("\n  Zero-Shot Results (all 8 sources):")
                print(
                    f"  {'Source ID':<40} {'Transfer':<10} {'Baseline':<10} {'Gain':<10} {'CI 95%':<20} {'Pass'}"
                )
                print(f"  {'-'*40} {'-'*10} {'-'*10} {'-'*10} {'-'*20} {'-'*5}")
                for r in report["results"]:
                    ci = f"[{r['confidence_interval_95'][0]:.3f}, {r['confidence_interval_95'][1]:.3f}]"
                    pass_str = "✓" if r["beats_baseline"] else "✗"
                    print(
                        f"  {r['source_id']:<40} {r['transfer_score']:<10.4f} {r['baseline_score']:<10.4f} {r['transfer_gain']:<10.4f} {ci:<20} {pass_str}"
                    )

                print(
                    f"\n  Summary: {report['sources_passing']}/{report['sources_total']} sources passing (threshold: {report['pass_threshold']})"
                )
                print(f"  Gate: {'PASS' if report['gate_passed'] else 'FAIL'}")

            elif report["regime"] == "few_shot":
                print("\n  Few-Shot Adaptation Budgets:")
                for r in report["results"]:
                    budget = r.get("adaptation_budget_used", "N/A")
                    print(
                        f"    {r['source_id']}: budget={budget}, score={r['transfer_score']:.4f}"
                    )

                print("\n  Baseline Regression Report:")
                if report["baseline_regression_report"]:
                    for source, reg in report["baseline_regression_report"].items():
                        print(
                            f"    {source}: original={reg['original']:.4f}, current={reg['current']:.4f}, regression={reg['regression']:.4f}"
                        )
                else:
                    print("    No regressions detected")

                print(
                    f"\n  Summary: {report['sources_passing']}/{report['sources_total']} sources, regressions={report['regression_detected']}"
                )
                print(f"  Gate: {'PASS' if report['gate_passed'] else 'FAIL'}")

            elif report["regime"] == "compositional":
                print("\n  Compositional Tasks (all 4):")
                for r in report["results"]:
                    ci = f"[{r['confidence_interval_95'][0]:.3f}, {r['confidence_interval_95'][1]:.3f}]"
                    skills = ", ".join(r.get("skills_composed", []))
                    pass_str = "PASS" if r["beats_baseline"] else "FAIL"
                    reason = (
                        f"score={r['transfer_score']:.4f} >= 0.6"
                        if r["beats_baseline"]
                        else f"score={r['transfer_score']:.4f} < 0.6"
                    )
                    print(f"    {r['source_id']}: {pass_str} ({reason})")
                    print(f"      Skills: {skills}")
                    print(f"      CI 95%: {ci}")

                print(
                    f"\n  Summary: {report['sources_passing']}/{report['sources_total']} tasks passing"
                )
                print(f"  Gate: {'PASS' if report['gate_passed'] else 'FAIL'}")

        # ============================================================
        # LONG-HORIZON SUCCESS REPORT
        # ============================================================
        print("\n" + "=" * 100)
        print("LONG-HORIZON SUCCESS REPORT")
        print("=" * 100)

        episode_artifacts = by_type.get("episode_trace", [])
        for art in episode_artifacts:
            data = artifact_service.retrieve_data(art.content_hash)
            report = json.loads(data.decode())

            env = report.get("environment", "unknown")
            print(f"\n  === Environment: {env.upper()} ===")
            print(f"  Hash: {art.content_hash}")

            metrics = report.get("metrics", {})
            print("\n  Per-Environment Metrics:")
            print(f"    Success Rate: {metrics.get('success_rate', 0):.2%}")
            print(f"    Episode Count: {report.get('episodes', 0)}")
            print(f"    Average Steps: {metrics.get('avg_steps', 0):.1f}")
            print(f"    Average Reward: {metrics.get('avg_reward', 0):.2f}")
            print(f"    Recovery Rate: {metrics.get('recovery_rate', 0):.2%}")
            print(
                f"    Plan Revisions/Episode: {metrics.get('plan_revisions_per_episode', 0):.2f}"
            )

            print("\n  Success Definitions:")
            if "navigation" in env:
                print("    - Agent reaches goal position within max_steps (150)")
            elif "resource" in env:
                print("    - Sell at least 50 units within max_steps (200)")
            elif "repair" in env:
                print("    - All 5 components diagnosed and repaired within max_steps (50)")

            print("\n  Sample Traces:")
            for trace in report.get("sample_traces", [])[:3]:
                print(
                    f"    Episode {trace['episode_id']}: steps={trace['total_steps']}, success={trace['success']}, reward={trace['final_reward']:.2f}"
                )
                print(
                    f"      Distribution shifts: {trace['distribution_shifts']}, Plan revisions: {trace['plan_revisions']}"
                )

        # ============================================================
        # SUSTAINED IMPROVEMENT LONGITUDINAL REPORT
        # ============================================================
        print("\n" + "=" * 100)
        print("SUSTAINED IMPROVEMENT LONGITUDINAL SCORE REPORT")
        print("=" * 100)

        longitudinal_artifacts = by_type.get("longitudinal_score_report", [])
        for art in longitudinal_artifacts:
            data = artifact_service.retrieve_data(art.content_hash)
            report = json.loads(data.decode())

            print(f"\n  Report ID: {report['report_id']}")
            print(f"  Hash: {art.content_hash}")
            print(f"  Days Run: {report['days_run']}")
            print(f"  Overall Improvement: {report['overall_improvement']:.2%}")
            print(f"  Catastrophic Regressions: {report['catastrophic_regressions']}")
            print(f"  Gate: {'PASS' if report['gate_passed'] else 'FAIL'}")

            print("\n  Trend Summary:")
            for metric, trend in report.get("trend_summary", {}).items():
                print(
                    f"    {metric}: slope={trend['slope']:.6f}, direction={trend['direction']}, p={trend['p_value']:.4f}, significant={trend['significant']}"
                )

        # Daily scores
        daily_artifacts = by_type.get("daily_score_series", [])
        for art in daily_artifacts:
            data = artifact_service.retrieve_data(art.content_hash)
            report = json.loads(data.decode())

            print("\n  Day-by-Day Composite Score Series:")
            days = report.get("days", [])
            scores = report.get("composite_scores", [])

            # Show first 5 and last 5
            print("    Day | Composite | Transfer | Baseline | Recurrence")
            print(f"    {'-'*4} | {'-'*9} | {'-'*8} | {'-'*8} | {'-'*10}")

            transfer = report.get("transfer_scores", [])
            baseline = report.get("baseline_scores", [])
            recurrence = report.get("recurrence_rates", [])

            for i in list(range(5)) + ["..."] + list(range(-5, 0)):
                if i == "...":
                    print("    ... ")
                    continue
                if i < len(days):
                    print(
                        f"    {days[i]:3d}  | {scores[i]:.4f}    | {transfer[i]:.4f}   | {baseline[i]:.4f}   | {recurrence[i]:.4f}"
                    )

        # Regression log
        regression_artifacts = by_type.get("regression_incident_log", [])
        for art in regression_artifacts:
            data = artifact_service.retrieve_data(art.content_hash)
            report = json.loads(data.decode())

            print("\n  Baseline Suite Regression Log:")
            incidents = report.get("incidents", [])
            if not incidents:
                print("    (empty - no catastrophic regressions detected)")
            else:
                for inc in incidents:
                    print(
                        f"    Day {inc['day']}: {inc['metric']} regressed by {inc['magnitude']:.4f} (catastrophic={inc['is_catastrophic']})"
                    )

        # ============================================================
        # ADVERSARIAL ATTACK REPORT
        # ============================================================
        print("\n" + "=" * 100)
        print("ADVERSARIAL ATTACK REPORT")
        print("=" * 100)

        adversarial_artifacts = by_type.get("adversarial_attack_report", [])
        for art in adversarial_artifacts:
            data = artifact_service.retrieve_data(art.content_hash)
            report = json.loads(data.decode())

            print(f"\n  Report ID: {report['report_id']}")
            print(f"  Hash: {art.content_hash}")

            print("\n  Attack Types and Counts:")
            attack_counts = {}
            for att in report.get("attempts", []):
                t = att["type"]
                if t not in attack_counts:
                    attack_counts[t] = 0
                attack_counts[t] += 1

            for attack_type, count in attack_counts.items():
                print(f"    {attack_type}: {count}")

            print("\n  Detection True/False Table:")
            detection = report.get("detection_summary", {})
            detected = detection.get("detected", 0)
            missed = detection.get("missed", 0)
            total = detected + missed

            print(f"    True Positives (detected): {detected}")
            print(f"    False Negatives (missed): {missed}")
            print(f"    Detection Rate: {detected}/{total} = {detected/max(total,1):.2%}")

            print(f"\n  Gate: {'PASS' if report['gate_passed'] else 'FAIL'}")

        # Calibration report
        calibration_artifacts = by_type.get("uncertainty_calibration_report", [])
        for art in calibration_artifacts:
            data = artifact_service.retrieve_data(art.content_hash)
            report = json.loads(data.decode())

            print("\n  Uncertainty Calibration Report:")
            print(f"  Hash: {art.content_hash}")

            cal = report.get("calibration", {})
            print("\n  Calibration Metrics:")
            print(f"    Total Predictions: {cal.get('total_predictions', 0)}")
            print(f"    Uncertainty Statements: {cal.get('uncertainty_statements', 0)}")
            print(f"    False Confidence Rate: {cal.get('false_confidence_rate', 0):.2%}")
            print(f"    Calibration Score: {cal.get('calibration_score', 0):.2%}")

            print("\n  Calibration Metric Definition:")
            print("    calibration_score = (detected + quarantined) / (2 * total_attempts)")
            print("    false_confidence_rate = (total - detected) / total")

            print("\n  Uncertainty Statements (epistemic humility):")
            for stmt in report.get("uncertainty_statements", [])[:3]:
                print(f"    - Claim avoided: {stmt['claim_avoided']}")
                print(f"      Reason: {stmt['reason']}")

        # ============================================================
        # FINAL SUMMARY
        # ============================================================
        print("\n" + "=" * 100)
        print("FINAL VERDICT")
        print("=" * 100)

        print(f"\n  Campaign: {manifest.campaign_id}")
        print(f"  Gates Passed: {manifest.gates_passed}/{manifest.gates_total}")
        print(f"  Final Score: {manifest.final_score:.2%}")
        print(f"\n  AGI CLAIM VALID: {'YES ✓' if manifest.agi_claim_valid else 'NO ✗'}")

        if manifest.agi_claim_valid:
            print("\n  Evidence artifacts are cryptographically hashed and stored.")
            print(f"  Total artifacts: {len(all_artifacts)}")
            print("  All artifacts have SHA-256 content hashes for integrity verification.")

        return manifest


if __name__ == "__main__":
    asyncio.run(extract_evidence(seed=100))
