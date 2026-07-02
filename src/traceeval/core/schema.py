from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from enum import Enum

class TrajectoryMode(str, Enum):
    """How strict the agent's tool execution path must be evaluated."""
    EXACT = "EXACT"           
    IN_ORDER = "IN_ORDER"     
    ANY_ORDER = "ANY_ORDER"  

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
    
class EDDTestCase(BaseModel):
    """
    The formal specification for a Vibe Coding test case.
    Replaces the vague (question, answer, context) RAG setup.
    """
    case_id: str
    input_prompt: str = Field(..., description="The user's initial natural language intent.")
    expected_skill: Optional[str] = Field(None, description="The Agent Skill that should have been triggered.")
    expected_tool_calls: List[ToolCall] = Field(default_factory=list)
    trajectory_mode: TrajectoryMode = Field(default=TrajectoryMode.IN_ORDER)
    rubric: List[str] = Field(
        ..., 
        min_length=1,
        description="List of natural language criteria for the LLM-as-a-judge (e.g., 'acknowledges duplicate', 'provides next step')"
    )

class AgentTrace(BaseModel):
    """
    The actual runtime trajectory captured from the agent (via OpenTelemetry/ADK).
    """
    session_id: str
    triggered_skills: List[str]
    executed_tools: List[ToolCall]
    final_output: str
    total_token_cost_usd: float = Field(ge=0.0)

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