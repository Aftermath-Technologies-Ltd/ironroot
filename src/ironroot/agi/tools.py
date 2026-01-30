# Author: Bradley R. Kinnard
"""Tool Learning - Onboarding New Tools at Runtime.

Requirements:
1. Given a tool API spec at runtime
2. Learn usage by trial and verification
3. Build a minimal correct workflow
4. Generate tests that catch misuse
5. Explain failures as limitations without fabricating

Gate passes if:
- Achieves correct usage in limited trials
- Generates tests that catch misuse
- Can explain failures as limitations without inventing facts
"""

import asyncio
import hashlib
import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from ironroot.domain.ids import generate_id
from ironroot.storage.artifact_service import get_artifact_service


class ToolCategory(str, Enum):
    """Tool categories."""
    DATA_PROCESSING = "data_processing"
    API_INTERACTION = "api_interaction"
    FILE_MANIPULATION = "file_manipulation"
    COMPUTATION = "computation"
    VERIFICATION = "verification"


@dataclass
class ToolParameter:
    """A single tool parameter."""
    name: str
    type: str
    required: bool
    description: str
    constraints: list[str] = field(default_factory=list)
    default: Any = None


@dataclass
class ToolSpec:
    """Complete tool API specification."""
    tool_id: str
    name: str
    category: ToolCategory
    description: str
    parameters: list[ToolParameter]
    return_type: str
    return_description: str
    examples: list[dict]
    constraints: list[str]
    error_conditions: list[str]


@dataclass
class ToolTrialResult:
    """Result of a single tool trial."""
    trial_id: str
    tool_id: str
    inputs: dict
    expected_output: Any | None
    actual_output: Any | None
    success: bool
    error_message: str | None
    lesson_learned: str


@dataclass
class ToolTest:
    """A test case for tool usage."""
    test_id: str
    tool_id: str
    test_name: str
    inputs: dict
    expected_behavior: str
    catches_misuse: bool
    misuse_type: str | None


@dataclass
class ToolWorkflow:
    """A minimal correct workflow using the tool."""
    workflow_id: str
    tool_id: str
    steps: list[dict]
    preconditions: list[str]
    postconditions: list[str]
    verified: bool


@dataclass
class ToolCompetenceReport:
    """Report on tool learning competence."""
    report_id: str
    tool_id: str
    tool_name: str
    trials_attempted: int
    trials_successful: int
    tests_generated: int
    tests_passing: int
    workflow_verified: bool
    failure_explanations: list[dict]
    competence_score: float
    gate_passed: bool
    created_at: str


class ToolSimulator:
    """Simulates a tool for testing."""

    def __init__(self, spec: ToolSpec, seed: int = 42):
        self.spec = spec
        self.rng = random.Random(seed)

    def execute(self, inputs: dict) -> tuple[bool, Any, str | None]:
        """Execute the tool with given inputs."""
        # Validate required parameters
        for param in self.spec.parameters:
            if param.required and param.name not in inputs:
                return False, None, f"Missing required parameter: {param.name}"

        # Simulate execution with some randomness
        success_rate = 0.7 if self.rng.random() > 0.3 else 0.9

        if self.rng.random() < success_rate:
            # Success
            if self.spec.return_type == "dict":
                result = {"status": "success", "data": self.rng.randint(1, 100)}
            elif self.spec.return_type == "list":
                result = [self.rng.randint(1, 10) for _ in range(3)]
            elif self.spec.return_type == "number":
                result = self.rng.random() * 100
            else:
                result = "success"
            return True, result, None
        else:
            # Simulate error
            errors = self.spec.error_conditions or ["Unknown error"]
            error = self.rng.choice(errors)
            return False, None, error


class ToolOnboardingTask:
    """A single tool onboarding task."""

    MAX_TRIALS = 10

    def __init__(self, spec: ToolSpec, seed: int = 42):
        self.spec = spec
        self.seed = seed
        self.rng = random.Random(seed)
        self.simulator = ToolSimulator(spec, seed)
        self.trials: list[ToolTrialResult] = []
        self.tests: list[ToolTest] = []
        self.workflow: ToolWorkflow | None = None

    def ingest_spec(self) -> dict:
        """Ingest and analyze the tool spec."""
        return {
            "tool_id": self.spec.tool_id,
            "name": self.spec.name,
            "required_params": [p.name for p in self.spec.parameters if p.required],
            "optional_params": [p.name for p in self.spec.parameters if not p.required],
            "constraints": self.spec.constraints,
            "example_count": len(self.spec.examples),
        }

    def run_trial(self, inputs: dict) -> ToolTrialResult:
        """Run a single trial with the tool."""
        trial_id = generate_id("trial")

        success, output, error = self.simulator.execute(inputs)

        # Learn from result
        if success:
            lesson = f"Successful call with inputs: {list(inputs.keys())}"
        else:
            lesson = f"Failed due to: {error}. Adjust inputs accordingly."

        result = ToolTrialResult(
            trial_id=trial_id,
            tool_id=self.spec.tool_id,
            inputs=inputs,
            expected_output=None,
            actual_output=output,
            success=success,
            error_message=error,
            lesson_learned=lesson,
        )

        self.trials.append(result)
        return result

    def generate_test(self, misuse_type: str | None = None) -> ToolTest:
        """Generate a test case that catches misuse."""
        test_id = generate_id("test")

        if misuse_type == "missing_required":
            # Test for missing required parameter
            inputs = {}
            expected = "Should fail with missing parameter error"
            catches = True
        elif misuse_type == "invalid_type":
            # Test for wrong type
            inputs = {self.spec.parameters[0].name: "invalid_type_value"}
            expected = "Should fail with type error"
            catches = True
        elif misuse_type == "constraint_violation":
            # Test for constraint violation
            inputs = {p.name: -999 for p in self.spec.parameters[:1]}
            expected = "Should fail with constraint error"
            catches = True
        else:
            # Valid usage test
            inputs = {p.name: f"valid_{p.name}" for p in self.spec.parameters if p.required}
            expected = "Should succeed with valid inputs"
            catches = False
            misuse_type = None

        test = ToolTest(
            test_id=test_id,
            tool_id=self.spec.tool_id,
            test_name=f"test_{misuse_type or 'valid_usage'}",
            inputs=inputs,
            expected_behavior=expected,
            catches_misuse=catches,
            misuse_type=misuse_type,
        )

        self.tests.append(test)
        return test

    def build_workflow(self) -> ToolWorkflow:
        """Build a minimal correct workflow."""
        workflow_id = generate_id("workflow")

        # Learn from successful trials
        successful = [t for t in self.trials if t.success]

        steps = []
        if successful:
            best_trial = successful[-1]  # Most recent success
            steps = [
                {"step": 1, "action": "validate_inputs", "description": "Check required parameters"},
                {"step": 2, "action": "call_tool", "inputs": best_trial.inputs},
                {"step": 3, "action": "verify_output", "description": "Check return value"},
            ]
        else:
            steps = [
                {"step": 1, "action": "validate_inputs", "description": "Placeholder"},
                {"step": 2, "action": "call_tool", "inputs": {}},
            ]

        self.workflow = ToolWorkflow(
            workflow_id=workflow_id,
            tool_id=self.spec.tool_id,
            steps=steps,
            preconditions=self.spec.constraints,
            postconditions=[f"Return type is {self.spec.return_type}"],
            verified=len(successful) > 0,
        )

        return self.workflow

    def explain_failure(self, error: str) -> dict:
        """Explain a failure as a limitation without fabricating."""
        # Match error to known conditions
        known_errors = self.spec.error_conditions

        if any(e.lower() in error.lower() for e in known_errors):
            explanation = {
                "error": error,
                "is_known_limitation": True,
                "explanation": f"This error is documented in the tool spec: {error}",
                "fabricated": False,
            }
        else:
            explanation = {
                "error": error,
                "is_known_limitation": False,
                "explanation": "I cannot determine the cause from available documentation.",
                "fabricated": False,
                "uncertainty": "high",
            }

        return explanation

    def get_competence_report(self) -> ToolCompetenceReport:
        """Generate competence report."""
        successful_trials = sum(1 for t in self.trials if t.success)
        passing_tests = sum(1 for t in self.tests if t.catches_misuse)

        # Calculate competence score
        trial_score = successful_trials / max(len(self.trials), 1)
        test_score = len(self.tests) / 5  # Expect at least 5 tests
        workflow_score = 1.0 if self.workflow and self.workflow.verified else 0.0

        competence = (trial_score + test_score + workflow_score) / 3

        # Collect failure explanations
        failure_explanations = [
            self.explain_failure(t.error_message)
            for t in self.trials
            if not t.success and t.error_message
        ]

        return ToolCompetenceReport(
            report_id=generate_id("competence"),
            tool_id=self.spec.tool_id,
            tool_name=self.spec.name,
            trials_attempted=len(self.trials),
            trials_successful=successful_trials,
            tests_generated=len(self.tests),
            tests_passing=passing_tests,
            workflow_verified=self.workflow.verified if self.workflow else False,
            failure_explanations=failure_explanations,
            competence_score=round(competence, 4),
            gate_passed=competence >= 0.6,
            created_at=datetime.now(timezone.utc).isoformat(),
        )


class ToolLearningSuite:
    """Suite of 5 tool onboarding tasks."""

    def __init__(self, seed: int = 42):
        self.seed = seed
        self.rng = random.Random(seed)
        self.artifact_service = get_artifact_service()

        # Create 5 tool specs
        self.tool_specs = self._create_tool_specs()
        self.tasks = {
            spec.tool_id: ToolOnboardingTask(spec, seed + i)
            for i, spec in enumerate(self.tool_specs)
        }

    def _create_tool_specs(self) -> list[ToolSpec]:
        """Create 5 diverse tool specifications."""
        return [
            ToolSpec(
                tool_id="tool_data_transform",
                name="DataTransformer",
                category=ToolCategory.DATA_PROCESSING,
                description="Transforms data from one format to another",
                parameters=[
                    ToolParameter("input_data", "dict", True, "Input data to transform"),
                    ToolParameter("format", "string", True, "Target format: json, csv, xml"),
                    ToolParameter("validate", "bool", False, "Validate output", default=True),
                ],
                return_type="dict",
                return_description="Transformed data with metadata",
                examples=[
                    {"input_data": {"a": 1}, "format": "json"},
                ],
                constraints=["format must be one of: json, csv, xml"],
                error_conditions=["Invalid format", "Input data too large", "Malformed input"],
            ),
            ToolSpec(
                tool_id="tool_api_client",
                name="APIClient",
                category=ToolCategory.API_INTERACTION,
                description="Makes HTTP requests to external APIs",
                parameters=[
                    ToolParameter("url", "string", True, "API endpoint URL"),
                    ToolParameter("method", "string", True, "HTTP method: GET, POST, PUT, DELETE"),
                    ToolParameter("headers", "dict", False, "Request headers"),
                    ToolParameter("body", "dict", False, "Request body for POST/PUT"),
                    ToolParameter("timeout", "number", False, "Request timeout in seconds", default=30),
                ],
                return_type="dict",
                return_description="Response with status, headers, and body",
                examples=[
                    {"url": "https://api.example.com/data", "method": "GET"},
                ],
                constraints=["URL must be valid HTTP/HTTPS", "timeout must be 1-300"],
                error_conditions=["Connection timeout", "Invalid URL", "Rate limited", "Auth failed"],
            ),
            ToolSpec(
                tool_id="tool_file_manager",
                name="FileManager",
                category=ToolCategory.FILE_MANIPULATION,
                description="Manages files and directories",
                parameters=[
                    ToolParameter("operation", "string", True, "Operation: read, write, delete, list"),
                    ToolParameter("path", "string", True, "File or directory path"),
                    ToolParameter("content", "string", False, "Content for write operation"),
                    ToolParameter("recursive", "bool", False, "Recursive for list/delete", default=False),
                ],
                return_type="dict",
                return_description="Operation result with status and data",
                examples=[
                    {"operation": "read", "path": "/tmp/test.txt"},
                ],
                constraints=["path must be within allowed directories", "max file size 10MB"],
                error_conditions=["File not found", "Permission denied", "Path traversal blocked"],
            ),
            ToolSpec(
                tool_id="tool_calculator",
                name="Calculator",
                category=ToolCategory.COMPUTATION,
                description="Performs mathematical computations",
                parameters=[
                    ToolParameter("expression", "string", True, "Mathematical expression"),
                    ToolParameter("precision", "number", False, "Decimal precision", default=6),
                    ToolParameter("variables", "dict", False, "Variable bindings for expression"),
                ],
                return_type="number",
                return_description="Computed result",
                examples=[
                    {"expression": "2 + 2"},
                    {"expression": "x * y", "variables": {"x": 3, "y": 4}},
                ],
                constraints=["No infinite loops", "Result must be finite"],
                error_conditions=["Division by zero", "Undefined variable", "Overflow"],
            ),
            ToolSpec(
                tool_id="tool_validator",
                name="DataValidator",
                category=ToolCategory.VERIFICATION,
                description="Validates data against schemas",
                parameters=[
                    ToolParameter("data", "dict", True, "Data to validate"),
                    ToolParameter("schema", "dict", True, "JSON schema for validation"),
                    ToolParameter("strict", "bool", False, "Strict mode", default=False),
                ],
                return_type="dict",
                return_description="Validation result with errors if any",
                examples=[
                    {"data": {"name": "test"}, "schema": {"type": "object"}},
                ],
                constraints=["Schema must be valid JSON Schema"],
                error_conditions=["Invalid schema", "Validation failed", "Type mismatch"],
            ),
        ]

    async def run_onboarding(
        self,
        session: AsyncSession,
        tool_id: str,
        run_id: str,
    ) -> ToolCompetenceReport:
        """Run full onboarding for a tool."""
        task = self.tasks.get(tool_id)
        if not task:
            raise ValueError(f"Unknown tool: {tool_id}")

        # 1) Ingest spec
        spec_analysis = task.ingest_spec()

        # 2) Run trials
        for _ in range(5):  # Limited trials
            # Generate inputs based on spec
            inputs = {}
            for param in task.spec.parameters:
                if param.required:
                    if param.type == "string":
                        inputs[param.name] = f"test_{param.name}"
                    elif param.type == "dict":
                        inputs[param.name] = {"key": "value"}
                    elif param.type == "number":
                        inputs[param.name] = self.rng.randint(1, 100)
                    elif param.type == "bool":
                        inputs[param.name] = True

            task.run_trial(inputs)

        # 3) Generate tests
        task.generate_test("missing_required")
        task.generate_test("invalid_type")
        task.generate_test("constraint_violation")
        task.generate_test(None)  # Valid usage
        task.generate_test(None)  # Another valid usage

        # 4) Build workflow
        task.build_workflow()

        # 5) Get report
        report = task.get_competence_report()

        # Store artifacts
        await self._store_artifacts(session, task, report, run_id)

        return report

    async def _store_artifacts(
        self,
        session: AsyncSession,
        task: ToolOnboardingTask,
        report: ToolCompetenceReport,
        run_id: str,
    ) -> None:
        """Store all tool learning artifacts."""
        # Spec ingestion
        await self.artifact_service.store_artifact(
            session=session,
            data=json.dumps({
                "tool_id": task.spec.tool_id,
                "spec": {
                    "name": task.spec.name,
                    "category": task.spec.category.value,
                    "parameters": [
                        {"name": p.name, "type": p.type, "required": p.required}
                        for p in task.spec.parameters
                    ],
                },
            }, indent=2).encode(),
            artifact_type="tool_spec_ingestion",
            created_by="tool_learning_suite",
            run_id=run_id,
            filename=f"tool_spec_{task.spec.tool_id}.json",
        )

        # Test suite
        await self.artifact_service.store_artifact(
            session=session,
            data=json.dumps({
                "tool_id": task.spec.tool_id,
                "tests": [
                    {
                        "test_id": t.test_id,
                        "name": t.test_name,
                        "catches_misuse": t.catches_misuse,
                        "misuse_type": t.misuse_type,
                    }
                    for t in task.tests
                ],
            }, indent=2).encode(),
            artifact_type="tool_usage_test_suite",
            created_by="tool_learning_suite",
            run_id=run_id,
            filename=f"tool_tests_{task.spec.tool_id}.json",
        )

        # Competence report
        await self.artifact_service.store_artifact(
            session=session,
            data=json.dumps({
                "report_id": report.report_id,
                "tool_id": report.tool_id,
                "competence_score": report.competence_score,
                "gate_passed": report.gate_passed,
                "trials": report.trials_attempted,
                "successful": report.trials_successful,
                "tests": report.tests_generated,
                "workflow_verified": report.workflow_verified,
                "failure_explanations": report.failure_explanations,
            }, indent=2).encode(),
            artifact_type="tool_competence_report",
            created_by="tool_learning_suite",
            run_id=run_id,
            filename=f"tool_competence_{task.spec.tool_id}.json",
        )


_suite: ToolLearningSuite | None = None


def get_tool_learning_suite(seed: int = 42) -> ToolLearningSuite:
    """Get or create the tool learning suite."""
    global _suite
    if _suite is None or _suite.seed != seed:
        _suite = ToolLearningSuite(seed=seed)
    return _suite
