# Author: Bradley R. Kinnard
"""AGI 5/5 Infrastructure.

Complete infrastructure for demonstrating general intelligence capabilities:
- 12 reality sources across 6 categories
- Zero-shot, few-shot, compositional transfer
- Long-horizon agency (50-200 step tasks)
- Tool learning and onboarding
- 30-day sustained improvement
- Adversarial robustness and epistemic humility

This is not AGI. This is infrastructure for measuring progress toward it.
"""

from ironroot.agi.reality_sources import (
    RealitySourceRegistry,
    get_reality_source_registry,
    SourceCategory,
)
from ironroot.agi.transfer import (
    TransferGate,
    TransferRegime,
    get_transfer_gate,
)
from ironroot.agi.agency import (
    LongHorizonEnvironment,
    get_agency_suite,
)
from ironroot.agi.tools import (
    ToolOnboardingTask,
    get_tool_learning_suite,
)
from ironroot.agi.sustained import (
    SustainedImprovementRunner,
    get_sustained_runner,
)
from ironroot.agi.adversarial import (
    AdversarialSuite,
    get_adversarial_suite,
)
from ironroot.agi.skills import (
    SkillLibrary,
    Skill,
    get_skill_library,
)
from ironroot.agi.ensemble import (
    WorldModelEnsemble,
    get_world_model_ensemble,
)

__all__ = [
    "RealitySourceRegistry",
    "get_reality_source_registry",
    "SourceCategory",
    "TransferGate",
    "TransferRegime",
    "get_transfer_gate",
    "LongHorizonEnvironment",
    "get_agency_suite",
    "ToolOnboardingTask",
    "get_tool_learning_suite",
    "SustainedImprovementRunner",
    "get_sustained_runner",
    "AdversarialSuite",
    "get_adversarial_suite",
    "SkillLibrary",
    "Skill",
    "get_skill_library",
    "WorldModelEnsemble",
    "get_world_model_ensemble",
]
