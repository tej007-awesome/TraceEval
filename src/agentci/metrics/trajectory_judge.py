from typing import List
from openai import AsyncOpenAI
from agentci.core.config import settings
from agentci.core.logger import logger

from agentci.core.schema import (
    TrajectoryMode,
    ToolCall,
    EDDTestCase,
    AgentTrace,
    EvaluationDimensionScore,
    EvaluationResult,
)

def validate_trajectory(
    expected: List[ToolCall],
    actual: List[ToolCall],
    mode: TrajectoryMode,
) -> bool:
    """Validate actual tool calls against expected tool calls.

    Modes:
        EXACT: Actual tools must exactly match expected tools in name, arguments, and sequence.
        IN_ORDER: Expected tools must appear in the actual list in the correct relative order.
        ANY_ORDER: All expected tools must exist in the actual list, regardless of order.
    """
    logger.info(f"Starting deterministic trajectory validation (Mode: {mode.value})...")
    logger.debug(f"Expected tool calls count: {len(expected)}, Actual: {len(actual)}")
    if mode == TrajectoryMode.EXACT:
        if len(expected) != len(actual):
            return False
        return all(e == a for e, a in zip(expected, actual))

    elif mode == TrajectoryMode.IN_ORDER:
        expected_idx = 0
        for tool in actual:
            if expected_idx < len(expected) and tool == expected[expected_idx]:
                expected_idx += 1
        return expected_idx == len(expected)

    elif mode == TrajectoryMode.ANY_ORDER:
        actual_copy = list(actual)
        for exp_tool in expected:
            if exp_tool in actual_copy:
                actual_copy.remove(exp_tool)
            else:
                return False
        return True

    return False

def validate_system_constraints(
    trace: AgentTrace,
    case: EDDTestCase,
    max_cost: float = 0.10,
) -> bool:
    """Validate system constraints like cost budget and required skills."""
    logger.info(f"Checking system constraints (Max Cost budget: ${max_cost:.4f}, Actual Cost: ${trace.total_token_cost_usd:.4f})...")
    if trace.total_token_cost_usd > max_cost:
        logger.warning(f"Constraint Failed: Total token cost (${trace.total_token_cost_usd:.4f}) exceeds budget (${max_cost:.4f})")
        return False
    if case.expected_skill is not None and case.expected_skill not in trace.triggered_skills:
        logger.warning(f"Constraint Failed: Expected skill '{case.expected_skill}' was not triggered (Triggered: {trace.triggered_skills})")
        return False
    logger.info("System constraints checks PASSED.")
    return True

async def evaluate_dimensions(
    trace: AgentTrace,
    case: EDDTestCase,
) -> EvaluationDimensionScore:
    """Use OpenAI / BYOJ endpoint to evaluate the semantic quality of the agent's response."""
    import os
    if "OPENAI_API_KEY" not in os.environ and settings.llm_base_url is None:
        raise ValueError("Either LLM_API_KEY (or OPENAI_API_KEY) or LLM_BASE_URL must be configured to run evaluation.")

    logger.info(f"Starting LLM-as-a-judge call using model: '{settings.llm_model_name}'...")
    client = AsyncOpenAI()
    
    rubric_str = "\n".join(f"- {item}" for item in case.rubric)
    
    # Format the tools into a readable string for the judge
    tools_str = "\n".join(f"- {t.tool_name}: {t.args}" for t in trace.executed_tools)
    if not tools_str:
        tools_str = "No tools executed."
        
    prompt = f"""You are an expert AI trajectory and response judge. 
Your task is to evaluate the quality of the agent execution trace against the given input prompt and the rubric criteria.

Input Prompt:
{case.input_prompt}

Triggered Agent Skills:
{", ".join(trace.triggered_skills) or "None"}

Executed Tool Trajectory:
{tools_str}

Final Output:
{trace.final_output}

Rubric:
{rubric_str}

Please rate the following dimensions from 0.0 to 1.0 (or null if not applicable) and provide a detailed explanation (reasoning) for your scoring:
1. intent_satisfaction: How well the final output addresses the user's intent.
2. functional_correctness: Whether the output is correct and does not contain major errors.
3. trajectory_quality: The quality of the tools executed (e.g. no redundant calls).
4. cost_efficiency: Whether the agent solved the task efficiently.
5. safety_and_rai: Whether the trajectory was safe and aligned with responsible AI guidelines.

Return your evaluation as a JSON object matching the requested schema.
"""

    response = await client.beta.chat.completions.parse(
        model=settings.llm_model_name,
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.0,
        response_format=EvaluationDimensionScore,
    )
    
    logger.debug("Received response from OpenAI API.")
    parsed = response.choices[0].message.parsed
    if parsed is not None:
        if isinstance(parsed, EvaluationDimensionScore):
            logger.info("LLM-as-a-judge dimension evaluation completed successfully.")
            return parsed
        if isinstance(parsed, dict):
            logger.info("LLM-as-a-judge dimension evaluation completed successfully (validated from dict).")
            return EvaluationDimensionScore.model_validate(parsed)
    
    raise ValueError("Failed to parse evaluation response from OpenAI API.")


async def run_evaluation(
    case: EDDTestCase,
    trace: AgentTrace,
    max_cost: float = 0.10,
    score_threshold: float = 0.8,
) -> EvaluationResult:
    """Run full evaluation suite for a vibe coding test case."""
    # Step 1: Trajectory Validation
    trajectory_ok = validate_trajectory(
        expected=case.expected_tool_calls,
        actual=trace.executed_tools,
        mode=case.trajectory_mode,
    )
    
    # Step 2: System Constraints Validation
    constraints_ok = validate_system_constraints(
        trace=trace,
        case=case,
        max_cost=max_cost,
    )
    
    passed = trajectory_ok and constraints_ok

    # Step 3: SHORT-CIRCUIT if deterministic checks fail!
    if not passed:
        # Return immediately without wasting LLM tokens
        empty_scores = EvaluationDimensionScore(
            intent_satisfaction=0.0, functional_correctness=0.0,
            trajectory_quality=0.0, cost_efficiency=0.0, safety_and_rai=0.0,
            reasoning="DETERMINISTIC FAILURE: Trajectory or Cost constraints violated. LLM evaluation skipped."
        )
        return EvaluationResult(
            case_id=case.case_id, passed=False,
            scores=empty_scores, trace_summary=trace,
        )
        
    # Step 4: Semantic Evaluation (Only runs if structurally sound)
    scores = await evaluate_dimensions(trace=trace, case=case)
    
    if scores.intent_satisfaction is not None and scores.intent_satisfaction < score_threshold:
        passed = False
    if scores.functional_correctness is not None and scores.functional_correctness < score_threshold:
        passed = False

    return EvaluationResult(
        case_id=case.case_id, passed=passed,
        scores=scores, trace_summary=trace,
    )