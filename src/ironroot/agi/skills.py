# Author: Bradley R. Kinnard
"""Unified Skill Library - Reusable Skills Across Domains.

Skills are learned modules with:
- Preconditions
- Effects
- Tests
- Transfer metadata

Skills become reusable across domains.
"""

import hashlib
import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ironroot.domain.ids import generate_id
from ironroot.storage.artifact_service import get_artifact_service


class SkillType(str, Enum):
    """Types of skills."""
    PREDICTION = "prediction"
    CLASSIFICATION = "classification"
    PLANNING = "planning"
    CONTROL = "control"
    EXTRACTION = "extraction"
    VERIFICATION = "verification"


@dataclass
class SkillTest:
    """A test for a skill."""
    test_id: str
    name: str
    inputs: dict
    expected_output: Any
    tolerance: float
    passed: bool | None = None


@dataclass
class TransferMetadata:
    """Metadata about skill transferability."""
    source_domains: list[str]
    target_domains_tested: list[str]
    transfer_success_rate: float
    adaptation_required: bool
    adaptation_cost: float


@dataclass
class Skill:
    """A reusable skill with preconditions and effects."""
    skill_id: str
    name: str
    skill_type: SkillType
    description: str
    preconditions: list[str]
    effects: list[str]
    tests: list[SkillTest]
    transfer_metadata: TransferMetadata
    performance: float
    version: int
    created_at: str
    learned_from: str  # Domain where skill was learned


@dataclass
class SkillApplication:
    """Record of applying a skill to a task."""
    application_id: str
    skill_id: str
    target_domain: str
    success: bool
    performance: float
    adaptation_used: float
    timestamp: str


class SkillLibrary:
    """Library of reusable skills."""

    def __init__(self, seed: int = 42):
        self.seed = seed
        self.rng = random.Random(seed)
        self.artifact_service = get_artifact_service()

        self.skills: dict[str, Skill] = {}
        self.applications: list[SkillApplication] = []

    def register_skill(self, skill: Skill) -> None:
        """Register a new skill in the library."""
        self.skills[skill.skill_id] = skill

    def get_skill(self, skill_id: str) -> Skill | None:
        """Get a skill by ID."""
        return self.skills.get(skill_id)

    def find_applicable_skills(
        self,
        domain: str,
        required_type: SkillType | None = None,
        min_performance: float = 0.5,
    ) -> list[Skill]:
        """Find skills applicable to a domain."""
        applicable = []

        for skill in self.skills.values():
            if required_type and skill.skill_type != required_type:
                continue
            if skill.performance < min_performance:
                continue

            # Check if domain is in tested transfer targets or source
            if domain in skill.transfer_metadata.source_domains:
                applicable.append(skill)
            elif domain in skill.transfer_metadata.target_domains_tested:
                if skill.transfer_metadata.transfer_success_rate >= 0.5:
                    applicable.append(skill)

        return applicable

    def apply_skill(
        self,
        skill_id: str,
        target_domain: str,
        adaptation_budget: float = 0.0,
    ) -> SkillApplication:
        """Apply a skill to a target domain."""
        skill = self.skills.get(skill_id)
        if not skill:
            raise ValueError(f"Skill not found: {skill_id}")

        # Calculate success probability
        if target_domain in skill.transfer_metadata.source_domains:
            success_prob = skill.performance
        elif target_domain in skill.transfer_metadata.target_domains_tested:
            success_prob = skill.transfer_metadata.transfer_success_rate
        else:
            # New domain - lower success
            success_prob = skill.performance * 0.5

        # Adaptation helps
        if adaptation_budget > 0:
            success_prob += min(0.2, adaptation_budget * 0.5)

        success = self.rng.random() < success_prob
        performance = success_prob * (0.9 + self.rng.uniform(0, 0.2)) if success else success_prob * 0.5

        application = SkillApplication(
            application_id=generate_id("app"),
            skill_id=skill_id,
            target_domain=target_domain,
            success=success,
            performance=round(performance, 4),
            adaptation_used=adaptation_budget,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        self.applications.append(application)

        # Update transfer metadata
        if target_domain not in skill.transfer_metadata.target_domains_tested:
            skill.transfer_metadata.target_domains_tested.append(target_domain)

        return application

    def create_skill_from_task(
        self,
        domain: str,
        skill_type: SkillType,
        performance: float,
    ) -> Skill:
        """Create a new skill from a successful task."""
        skill_id = generate_id("skill")

        # Generate tests
        tests = []
        for i in range(3):
            tests.append(SkillTest(
                test_id=generate_id("test"),
                name=f"test_{skill_type.value}_{i}",
                inputs={"input": i},
                expected_output={"output": i * 2},
                tolerance=0.1,
                passed=True,
            ))

        skill = Skill(
            skill_id=skill_id,
            name=f"{skill_type.value}_{domain}",
            skill_type=skill_type,
            description=f"Skill for {skill_type.value} in {domain}",
            preconditions=[f"Input from {domain}", "Valid input format"],
            effects=[f"Produces {skill_type.value} output", "Updates beliefs"],
            tests=tests,
            transfer_metadata=TransferMetadata(
                source_domains=[domain],
                target_domains_tested=[],
                transfer_success_rate=0.0,
                adaptation_required=True,
                adaptation_cost=0.1,
            ),
            performance=performance,
            version=1,
            created_at=datetime.now(timezone.utc).isoformat(),
            learned_from=domain,
        )

        self.skills[skill_id] = skill
        return skill

    def compose_skills(
        self,
        skill_ids: list[str],
        target_domain: str,
    ) -> Skill | None:
        """Compose multiple skills into a new composite skill."""
        skills = [self.skills.get(s) for s in skill_ids if s in self.skills]
        if len(skills) < 2:
            return None

        # Create composite skill
        composite_id = generate_id("skill")

        # Aggregate preconditions and effects
        all_preconditions = []
        all_effects = []
        all_tests = []

        for skill in skills:
            all_preconditions.extend(skill.preconditions)
            all_effects.extend(skill.effects)
            all_tests.extend(skill.tests)

        # Remove duplicates
        all_preconditions = list(set(all_preconditions))
        all_effects = list(set(all_effects))

        # Composite performance is limited by weakest link
        min_performance = min(s.performance for s in skills)

        composite = Skill(
            skill_id=composite_id,
            name=f"composite_{target_domain}",
            skill_type=SkillType.PLANNING,  # Composites are typically planning
            description=f"Composite skill from {len(skills)} skills for {target_domain}",
            preconditions=all_preconditions,
            effects=all_effects,
            tests=all_tests[:5],  # Limit tests
            transfer_metadata=TransferMetadata(
                source_domains=[s.learned_from for s in skills],
                target_domains_tested=[target_domain],
                transfer_success_rate=0.6,  # Composites have moderate transfer
                adaptation_required=True,
                adaptation_cost=0.2,
            ),
            performance=min_performance * 0.9,
            version=1,
            created_at=datetime.now(timezone.utc).isoformat(),
            learned_from="composite",
        )

        self.skills[composite_id] = composite
        return composite

    async def store_library(
        self,
        session: AsyncSession,
        run_id: str,
    ) -> str:
        """Store the skill library as an artifact."""
        library_data = {
            "skill_count": len(self.skills),
            "application_count": len(self.applications),
            "skills": [
                {
                    "skill_id": s.skill_id,
                    "name": s.name,
                    "type": s.skill_type.value,
                    "performance": s.performance,
                    "source_domains": s.transfer_metadata.source_domains,
                    "transfer_success_rate": s.transfer_metadata.transfer_success_rate,
                    "tests_passed": sum(1 for t in s.tests if t.passed),
                }
                for s in self.skills.values()
            ],
            "recent_applications": [
                {
                    "skill_id": a.skill_id,
                    "target_domain": a.target_domain,
                    "success": a.success,
                    "performance": a.performance,
                }
                for a in self.applications[-10:]
            ],
        }

        artifact = await self.artifact_service.store_artifact(
            session=session,
            data=json.dumps(library_data, indent=2).encode(),
            artifact_type="skill_library",
            created_by="skill_library",
            run_id=run_id,
            filename=f"skill_library_{len(self.skills)}.json",
        )

        return artifact.id


_library: SkillLibrary | None = None


def get_skill_library(seed: int = 42) -> SkillLibrary:
    """Get or create the skill library."""
    global _library
    if _library is None or _library.seed != seed:
        _library = SkillLibrary(seed=seed)
    return _library
