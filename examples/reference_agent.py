from agentci.core.schema import AgentTrace, ToolCall

def process_refund(prompt: str) -> AgentTrace:
    """
    A mock live agent. It takes a prompt and simulates executing tools.
    """
    # 1. The agent "thinks" and decides to call tools...
    executed_tools = [
        ToolCall(tool_name="lookup_order", args={"order_id": "4521"}),
        ToolCall(tool_name="check_duplicate_charge", args={"order_id": "4521"}),
        ToolCall(tool_name="issue_refund", args={"order_id": "4521", "amount": "full"})
    ]
    
    # 2. The agent generates a final string...
    output = "I have verified the duplicate charge. A full refund for order #4521 has been issued."
    
    # 3. It returns the OTel trace data conforming to our schema.
    return AgentTrace(
        session_id="live_sess_001",
        triggered_skills=["refund-processor"],
        executed_tools=executed_tools,
        final_output=output,
        total_token_cost_usd=0.015
    )