"""Pydantic models for the benchmark's scenario file format and operator results.

A scenario file (benchmarks/scenarios/<domain>/<id>.json) is the unit of authoring: one
clean (case, trace) pair plus hand-authored gate-2 variants. Fault operators and benign
controls (benchmarks/operators.py) are seeded functions over a loaded Scenario, never
generators of new content - see scenarios/AUTHORING.md for the authoring contract.
"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from traceeval.core.schema import AgentTrace, EDDTestCase, FailureCode

GATE2_VARIANT_KINDS = (
    "incorrect_final_answer",
    "rubric_item_ignored",
    "unsafe_content_in_output",
    "paraphrased_but_correct_final_answer",
    "hallucinated_action",
)


class Gate2Variant(BaseModel):
    """A hand-authored alternate final_output (and, for hallucinated_action, a trace
    mutation) used by the gate-2 fault operators and the paraphrase benign control.
    Never machine-generated - see scenarios/AUTHORING.md."""

    kind: Literal[
        "incorrect_final_answer",
        "rubric_item_ignored",
        "unsafe_content_in_output",
        "paraphrased_but_correct_final_answer",
        "hallucinated_action",
    ]
    final_output: str = Field(..., min_length=1)
    expected_passed: bool = Field(
        ..., description="True only for paraphrased_but_correct_final_answer (a benign control)."
    )
    expected_dimension: Optional[str] = Field(
        None,
        description="Snake_case EvaluationDimensionScore field this variant should fail on "
        "(required for fault variants; must be None for paraphrased_but_correct_final_answer).",
    )
    soft_action_tool: Optional[str] = Field(
        None,
        description="hallucinated_action only: tool name to remove from executed_tools. Must "
        "NOT appear in the scenario's case.expected_tool_calls (a 'soft', rubric-only action) - "
        "checked at scenario-load time, not just at operator-apply time.",
    )
    note: str = Field(
        "", description="Authoring rationale: what fact/rubric item/dimension this targets."
    )

    @model_validator(mode="after")
    def _validate_kind_fields(self) -> "Gate2Variant":
        is_paraphrase = self.kind == "paraphrased_but_correct_final_answer"
        if is_paraphrase:
            if not self.expected_passed:
                raise ValueError("paraphrased_but_correct_final_answer must have expected_passed=True")
            if self.expected_dimension is not None:
                raise ValueError("paraphrased_but_correct_final_answer must not set expected_dimension")
        else:
            if self.expected_passed:
                raise ValueError(f"{self.kind} is a fault variant and must have expected_passed=False")
            if not self.expected_dimension:
                raise ValueError(f"{self.kind} must set expected_dimension (which dimension it targets)")
        if self.kind == "hallucinated_action" and not self.soft_action_tool:
            raise ValueError("hallucinated_action must set soft_action_tool")
        if self.kind != "hallucinated_action" and self.soft_action_tool:
            raise ValueError("soft_action_tool is only valid for hallucinated_action")
        return self


class Scenario(BaseModel):
    """One base scenario: a clean (case, trace) pair plus hand-authored gate-2 variants."""

    id: str = Field(..., min_length=1)
    domain: str = Field(..., min_length=1)
    case: EDDTestCase
    trace: AgentTrace
    gate2_variants: List[Gate2Variant] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_soft_action_tools(self) -> "Scenario":
        expected_names = {tc.tool_name for tc in self.case.expected_tool_calls}
        for variant in self.gate2_variants:
            if variant.soft_action_tool and variant.soft_action_tool in expected_names:
                raise ValueError(
                    f"hallucinated_action soft_action_tool '{variant.soft_action_tool}' must not "
                    f"appear in case.expected_tool_calls (it would degenerate into skipped_step, "
                    f"which gate 1 already catches before gate 2 runs)"
                )
            if variant.soft_action_tool and not any(
                tc.tool_name == variant.soft_action_tool for tc in self.trace.executed_tools
            ):
                raise ValueError(
                    f"hallucinated_action soft_action_tool '{variant.soft_action_tool}' does not "
                    f"appear in the clean trace's executed_tools - nothing to remove"
                )
        return self


class EvalOutcome(BaseModel):
    """What actually happened when a mutated (case, trace) from an OperatorResult was run
    through TraceEval's real run_evaluation. One per (scenario, operator, k)."""

    scenario_id: str
    domain: str
    operator: str
    category: Literal["gate1_fault", "gate2_fault", "benign"]
    k: int = 0

    expected_passed: bool
    expected_gate: Optional[Literal["gate1", "gate2"]] = None
    expected_code: Optional[FailureCode] = None
    expected_dimension: Optional[str] = None
    label: str = ""

    actual_passed: bool
    actual_codes: List[str] = Field(default_factory=list)
    actual_dimensions: List[str] = Field(default_factory=list)
    is_judge_error: bool = False
    sentinel_triggered: bool = False
    retries: int = 0
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    error_message: Optional[str] = None
    from_cache: bool = False


class OperatorResult(BaseModel):
    """The outcome of applying one operator to one scenario."""

    scenario_id: str
    domain: str
    operator: str
    category: Literal["gate1_fault", "gate2_fault", "benign"]
    applicable: bool
    inapplicable_reason: Optional[str] = None

    mutated_case: Optional[EDDTestCase] = None
    mutated_trace: Optional[AgentTrace] = None

    expected_passed: Optional[bool] = None
    expected_gate: Optional[Literal["gate1", "gate2"]] = None
    expected_code: Optional[FailureCode] = None
    expected_dimension: Optional[str] = None
    label: str = ""
