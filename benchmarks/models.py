"""Pydantic models for the benchmark's scenario file format and operator results.

A scenario file (benchmarks/scenarios/<domain>/<id>.json) is the unit of authoring: one
clean (case, trace) pair plus hand-authored gate-2 variants. Fault operators and benign
controls (benchmarks/operators.py) are seeded functions over a loaded Scenario, never
generators of new content - see scenarios/AUTHORING.md for the authoring contract.
"""
from __future__ import annotations

from typing import Dict, List, Literal, Optional

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
    expected_dimensions: List[str] = Field(
        default_factory=list,
        description="Snake_case EvaluationDimensionScore field(s) this variant should fail on "
        "(required, non-empty for fault variants; must be empty for "
        "paraphrased_but_correct_final_answer). Attribution succeeds if the judge's "
        "JUDGE_BELOW_THRESHOLD result names ANY of these dimensions - some variants "
        "legitimately touch more than one (e.g. rubric_item_ignored can plausibly read as "
        "either an intent or a correctness miss).",
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

    @model_validator(mode="before")
    @classmethod
    def _coerce_singular_dimension(cls, data):
        # Backward compat: old scenario files use the singular "expected_dimension" string
        # field. Accept it and normalize to the new expected_dimensions list, so existing
        # scenario JSON (and any author still following the older convention) keeps loading.
        if isinstance(data, dict) and "expected_dimension" in data and "expected_dimensions" not in data:
            data = dict(data)
            val = data.pop("expected_dimension")
            data["expected_dimensions"] = [val] if val else []
        return data

    @model_validator(mode="after")
    def _validate_kind_fields(self) -> "Gate2Variant":
        is_paraphrase = self.kind == "paraphrased_but_correct_final_answer"
        if is_paraphrase:
            if not self.expected_passed:
                raise ValueError("paraphrased_but_correct_final_answer must have expected_passed=True")
            if self.expected_dimensions:
                raise ValueError("paraphrased_but_correct_final_answer must not set expected_dimensions")
        else:
            if self.expected_passed:
                raise ValueError(f"{self.kind} is a fault variant and must have expected_passed=False")
            if not self.expected_dimensions:
                raise ValueError(f"{self.kind} must set expected_dimensions (which dimension(s) it targets)")
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
    expected_dimensions: List[str] = Field(default_factory=list)
    label: str = ""

    actual_passed: bool
    actual_codes: List[str] = Field(default_factory=list)
    actual_dimensions: List[str] = Field(default_factory=list)
    actual_below_threshold_dimensions: List[str] = Field(
        default_factory=list,
        description="Dimensions specifically from JUDGE_BELOW_THRESHOLD failures (a subset of "
        "actual_dimensions, which also includes JUDGE_NULL_DIMENSION) - attribution correctness "
        "is checked against this narrower list, not any dimension the judge merely mentioned.",
    )
    gate1_passed: bool = Field(
        True,
        description="Whether gate 1 alone passed - derived from whether any NON-judge "
        "FailureCode appears in actual_codes. False only when a real gate-1 failure code "
        "(ARG_MISMATCH, COST_EXCEEDED, etc.) is present, which - per run_evaluation's "
        "short-circuit - also implies actual_passed=False. True means gate 1 passed and the "
        "item reached gate 2 for real (whether gate 2 then passed or failed), which is the "
        "signal used to separate 'Gate-1 FP' from 'Pipeline FP' and to decide whether an "
        "item's cost/latency/judge-error stats belong in the judge-call aggregates.",
    )
    judge_reasoning: Optional[str] = Field(
        None, description="scores.reasoning from the real judge call, saved only when "
        "expected_passed != actual_passed (a gate-2 miss or a pipeline false positive), so "
        "failures can be analysed without re-spending."
    )
    actual_scores: Optional[Dict[str, Optional[float]]] = Field(
        None, description="The judge's per-dimension scores, saved under the same condition "
        "as judge_reasoning."
    )
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
    expected_dimensions: List[str] = Field(default_factory=list)
    label: str = ""
