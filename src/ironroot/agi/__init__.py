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

from ironroot.agi.adversarial import (
    AdversarialSuite,
    get_adversarial_suite,
)
from ironroot.agi.agency import (
    LongHorizonEnvironment,
    get_agency_suite,
)
from ironroot.agi.ensemble import (
    WorldModelEnsemble,
    get_world_model_ensemble,
)
from ironroot.agi.reality_sources import (
    RealitySourceRegistry,
    SourceCategory,
    get_reality_source_registry,
)
from ironroot.agi.skills import (
    Skill,
    SkillLibrary,
    get_skill_library,
)
from ironroot.agi.sustained import (
    SustainedImprovementRunner,
    get_sustained_runner,
)
from ironroot.agi.tools import (
    ToolOnboardingTask,
    get_tool_learning_suite,
)
from ironroot.agi.transfer import (
    TransferGate,
    TransferRegime,
    get_transfer_gate,
)

__all__ = [
    "AdversarialSuite",
    "LongHorizonEnvironment",
    "RealitySourceRegistry",
    "Skill",
    "SkillLibrary",
    "SourceCategory",
    "SustainedImprovementRunner",
    "ToolOnboardingTask",
    "TransferGate",
    "TransferRegime",
    "WorldModelEnsemble",
    "get_adversarial_suite",
    "get_agency_suite",
    "get_reality_source_registry",
    "get_skill_library",
    "get_sustained_runner",
    "get_tool_learning_suite",
    "get_transfer_gate",
    "get_world_model_ensemble",
]
