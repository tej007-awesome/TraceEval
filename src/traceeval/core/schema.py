from __future__ import annotations
import re
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Dict, Any, Optional
from enum import Enum

class TrajectoryMode(str, Enum):
    """How strict the agent's tool execution path must be evaluated."""
    EXACT = "EXACT"
    IN_ORDER = "IN_ORDER"
    ANY_ORDER = "ANY_ORDER"

class ArgMatchMode(str, Enum):
    """How an expected tool call's arguments are compared against the actual call."""
    EXACT = "EXACT"
    SUBSET = "SUBSET"
    REGEX = "REGEX"
    ANY = "ANY"

class FailureCode(str, Enum):
    """Machine-readable classification for a deterministic gate failure."""
    TRAJECTORY_LENGTH_MISMATCH = "TRAJECTORY_LENGTH_MISMATCH"
    TRAJECTORY_STEP_MISMATCH = "TRAJECTORY_STEP_MISMATCH"
    ARG_MISMATCH = "ARG_MISMATCH"
    TOOL_CALL_NEVER_CALLED = "TOOL_CALL_NEVER_CALLED"
    TOOL_CALL_OUT_OF_ORDER = "TOOL_CALL_OUT_OF_ORDER"
    TOOL_CALL_NOT_FOUND = "TOOL_CALL_NOT_FOUND"
    FORBIDDEN_TOOL_CALLED = "FORBIDDEN_TOOL_CALLED"
    FORBIDDEN_ARGS = "FORBIDDEN_ARGS"
    COST_EXCEEDED = "COST_EXCEEDED"
    COST_INCOMPLETE = "COST_INCOMPLETE"
    SKILL_NOT_TRIGGERED = "SKILL_NOT_TRIGGERED"

class FailureReason(BaseModel):
    """Structured detail for a single failure, carried alongside the plain-text reason string."""
    code: FailureCode
    message: str
    step_index: Optional[int] = Field(None, description="Index into the ACTUAL trace, if a single actual step is implicated.")
    expected_index: Optional[int] = Field(None, description="Index into expected_tool_calls, if a single expected call is implicated.")
    span_id: Optional[str] = None
    expected: Optional[Any] = None
    actual: Optional[Any] = None

class CheckResult(BaseModel):
    """Outcome of a single deterministic gate, with human-readable reasons on failure."""
    passed: bool
    reasons: List[str] = []
    reason_details: List[FailureReason] = Field(default_factory=list)

class GoldenRecord(BaseModel):
    meta_id: str
    scenario_type: str
    expected_passed: bool
    expected_failure_reason: Optional[str] = None
    case: EDDTestCase
    trace: AgentTrace

class ToolCall(BaseModel):
    """Represents a single tool invocation (MCP or local)."""
    tool_name: str
    args: Dict[str, Any]
    span_id: Optional[str] = None

class ExpectedToolCall(ToolCall):
    """A ToolCall expectation with a configurable argument-matching strategy."""
    arg_match_mode: ArgMatchMode = ArgMatchMode.EXACT
    field_overrides: Dict[str, ArgMatchMode] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_field_overrides_and_regex(self) -> "ExpectedToolCall":
        for key in self.field_overrides:
            if key not in self.args:
                raise ValueError(f"field_overrides references arg '{key}' not present in args")
        for key, val in self.args.items():
            mode = self.field_overrides.get(key, self.arg_match_mode)
            if mode == ArgMatchMode.REGEX:
                if not isinstance(val, str):
                    raise ValueError(f"regex pattern for arg '{key}' must be a string, got {type(val).__name__}")
                try:
                    re.compile(val)
                except re.error as e:
                    raise ValueError(f"invalid regex pattern for arg '{key}': {e}")
        return self

class EDDTestCase(BaseModel):
    """
    The formal specification for a Vibe Coding test case.
    Replaces the vague (question, answer, context) RAG setup.
    """
    case_id: str
    input_prompt: str = Field(..., description="The user's initial natural language intent.")
    expected_skill: Optional[str] = Field(None, description="The Agent Skill that should have been triggered.")
    expected_tool_calls: List[ExpectedToolCall] = Field(default_factory=list)
    trajectory_mode: TrajectoryMode = Field(default=TrajectoryMode.IN_ORDER)
    forbidden_tools: List[str] = Field(default_factory=list, description="Tool names that must never appear in the trajectory.")
    forbidden_args: Dict[str, List[Dict[str, str]]] = Field(
        default_factory=dict,
        description="Per-tool list of arg-name -> regex-pattern rule-sets; a call is forbidden if all patterns in any one rule-set match.",
    )
    rubric: List[str] = Field(
        ...,
        min_length=1,
        description="List of natural language criteria for the LLM-as-a-judge (e.g., 'acknowledges duplicate', 'provides next step')"
    )

    @field_validator("expected_tool_calls", mode="before")
    @classmethod
    def _coerce_expected_tool_calls(cls, v: Any) -> Any:
        # Pydantic v2 rejects a base-class ToolCall instance where a subclass
        # (ExpectedToolCall) is declared. Existing callers construct EDDTestCase with plain
        # ToolCall objects in expected_tool_calls, so convert those to dicts here and let
        # normal validation re-build them as ExpectedToolCall with default matching mode.
        if not isinstance(v, list):
            return v
        out = []
        for item in v:
            if isinstance(item, ExpectedToolCall):
                out.append(item)
            elif isinstance(item, ToolCall):
                out.append(item.model_dump())
            else:
                out.append(item)
        return out

    @model_validator(mode="after")
    def _validate_forbidden(self) -> "EDDTestCase":
        for tool_name, rulesets in self.forbidden_args.items():
            for ruleset in rulesets:
                for arg_name, pattern in ruleset.items():
                    try:
                        re.compile(pattern)
                    except re.error as e:
                        raise ValueError(
                            f"invalid regex in forbidden_args['{tool_name}']['{arg_name}']: {e}"
                        )
        expected_names = {tc.tool_name for tc in self.expected_tool_calls}
        overlap = expected_names & set(self.forbidden_tools)
        if overlap:
            raise ValueError(
                f"tool(s) {sorted(overlap)} appear in both expected_tool_calls and forbidden_tools"
            )
        for tc in self.expected_tool_calls:
            for ruleset in self.forbidden_args.get(tc.tool_name, []):
                match = True
                for arg_name, pattern in ruleset.items():
                    if arg_name not in tc.args:
                        match = False
                        break
                    eff_mode = tc.field_overrides.get(arg_name, tc.arg_match_mode)
                    if eff_mode not in (ArgMatchMode.EXACT, ArgMatchMode.SUBSET):
                        match = False
                        break
                    if not re.search(pattern, str(tc.args[arg_name])):
                        match = False
                        break
                if match:
                    raise ValueError(
                        f"expected_tool_call '{tc.tool_name}' contradicts forbidden_args rule-set {ruleset}"
                    )
        return self

class AgentTrace(BaseModel):
    """
    The actual runtime trajectory captured from the agent (via OpenTelemetry/ADK).
    """
    session_id: str
    triggered_skills: List[str]
    executed_tools: List[ToolCall]
    final_output: str
    total_token_cost_usd: float = Field(ge=0.0)
    cost_complete: bool = True

class EvaluationDimensionScore(BaseModel):
    """Scores mapped directly to the 5 dimensions of Vibe Coding Evaluation."""
    intent_satisfaction: Optional[float] = Field(None, ge=0.0, le=1.0)
    functional_correctness: Optional[float] = Field(None, ge=0.0, le=1.0)
    trajectory_quality: Optional[float] = Field(None, ge=0.0, le=1.0)
    cost_efficiency: Optional[float] = Field(None, ge=0.0, le=1.0)
    safety_and_rai: Optional[float] = Field(None, ge=0.0, le=1.0)
    reasoning: str = Field(..., description="The judge's justification for the scores.")

class EvaluationResult(BaseModel):
    """The final output payload for TraceEval."""
    case_id: str
    passed: bool
    scores: EvaluationDimensionScore
    trace_summary: AgentTrace
    failures: List[str] = []
    failure_details: List[FailureReason] = Field(default_factory=list)