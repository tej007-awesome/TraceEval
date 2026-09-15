"""OpenTelemetry GenAI Semantic Convention Attribute Names.

Note: The OpenTelemetry GenAI semantic conventions are still evolving.
All attribute names and operation constants are centralized in this module
to maintain a single source of truth for OTEL trace parsing.
"""

GEN_AI_OPERATION_NAME = "gen_ai.operation.name"
GEN_AI_TOOL_NAME = "gen_ai.tool.name"
GEN_AI_TOOL_CALL_ARGUMENTS = "gen_ai.tool.call.arguments"
GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_AGENT_NAME = "gen_ai.agent.name"
GEN_AI_CONVERSATION_ID = "gen_ai.conversation.id"
GEN_AI_OUTPUT_MESSAGES = "gen_ai.output.messages"

OPERATION_INVOKE_AGENT = "invoke_agent"
OPERATION_CHAT = "chat"
OPERATION_EXECUTE_TOOL = "execute_tool"
