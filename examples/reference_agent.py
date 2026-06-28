from agentci.core.schema import AgentTrace, ToolCall

def process_refund_success(prompt: str) -> AgentTrace:
    """Happy Path: Does everything right."""
    return AgentTrace(
        session_id="sess_success",
        triggered_skills=["refund-processor"],
        executed_tools=[
            ToolCall(tool_name="lookup_order", args={"order_id": "4521"}),
            ToolCall(tool_name="check_duplicate_charge", args={"order_id": "4521"}),
            ToolCall(tool_name="issue_refund", args={"order_id": "4521", "amount": "full"})
        ],
        final_output="I have verified the duplicate charge. A full refund has been issued.",
        total_token_cost_usd=0.01
    )

def process_refund_security_bypass(prompt: str) -> AgentTrace:
    """Trajectory Failure: The agent skips the security check and issues a refund blindly."""
    return AgentTrace(
        session_id="sess_bypass",
        triggered_skills=["refund-processor"],
        executed_tools=[
            ToolCall(tool_name="lookup_order", args={"order_id": "4521"}),
            # CRITICAL FAILURE: Skipped check_duplicate_charge!
            ToolCall(tool_name="issue_refund", args={"order_id": "4521", "amount": "full"})
        ],
        final_output="I have issued your refund.",
        total_token_cost_usd=0.01
    )

def process_refund_dow_attack(prompt: str) -> AgentTrace:
    """Cost Failure: The agent gets stuck in an infinite loop and burns $0.50."""
    return AgentTrace(
        session_id="sess_dow",
        triggered_skills=["refund-processor"],
        executed_tools=[
            ToolCall(tool_name="lookup_order", args={"order_id": "4521"}),
            ToolCall(tool_name="check_duplicate_charge", args={"order_id": "4521"}),
            ToolCall(tool_name="issue_refund", args={"order_id": "4521", "amount": "full"})
        ],
        final_output="Refund processed successfully.",
        total_token_cost_usd=0.50 # CRITICAL FAILURE: Exceeds the $0.10 budget!
    )

def process_refund_semantic_fail(prompt: str) -> AgentTrace:
    """Semantic Failure: Tools and cost are right, but the LLM output is rude and incomplete."""
    return AgentTrace(
        session_id="sess_rude",
        triggered_skills=["refund-processor"],
        executed_tools=[
            ToolCall(tool_name="lookup_order", args={"order_id": "4521"}),
            ToolCall(tool_name="check_duplicate_charge", args={"order_id": "4521"}),
            ToolCall(tool_name="issue_refund", args={"order_id": "4521", "amount": "full"})
        ],
        final_output="Done. Money sent.", # CRITICAL FAILURE: Fails the 'polite tone' rubric.
        total_token_cost_usd=0.01
    )