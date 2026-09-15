import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from traceeval.core.logger import logger
from traceeval.core.schema import AgentTrace, ToolCall
from traceeval.pricing import DEFAULT_PRICING, ModelPrice, compute_cost
import traceeval.loaders.otel_attributes as otel_attrs


class TokenUsage(BaseModel):
    model: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class OtelLoadResult(BaseModel):
    trace: AgentTrace
    token_usage: List[TokenUsage] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


def _get_attribute_value(val_dict: Any) -> Any:
    if not isinstance(val_dict, dict):
        return val_dict
    if "stringValue" in val_dict:
        return val_dict["stringValue"]
    if "intValue" in val_dict:
        val = val_dict["intValue"]
        try:
            return int(val)
        except (ValueError, TypeError):
            return val
    if "doubleValue" in val_dict:
        val = val_dict["doubleValue"]
        try:
            return float(val)
        except (ValueError, TypeError):
            return val
    if "boolValue" in val_dict:
        return bool(val_dict["boolValue"])
    if "arrayValue" in val_dict:
        values = val_dict.get("arrayValue", {}).get("values", [])
        return [_get_attribute_value(v) for v in values]
    if "kvlistValue" in val_dict:
        values = val_dict.get("kvlistValue", {}).get("values", [])
        return {
            item["key"]: _get_attribute_value(item.get("value", {}))
            for item in values
            if "key" in item
        }
    return None


def _extract_span_attributes(span: dict) -> Dict[str, Any]:
    attrs = {}
    for attr in span.get("attributes", []):
        key = attr.get("key")
        if key:
            attrs[key] = _get_attribute_value(attr.get("value", {}))
    return attrs


def _extract_text_content(val: Any) -> str:
    if isinstance(val, str):
        val_str = val.strip()
        if (val_str.startswith("{") and val_str.endswith("}")) or (
            val_str.startswith("[") and val_str.endswith("]")
        ):
            try:
                parsed = json.loads(val_str)
                return _extract_text_content(parsed)
            except Exception:
                return val_str
        return val_str
    elif isinstance(val, list):
        parts = []
        for item in val:
            extracted = _extract_text_content(item)
            if extracted:
                parts.append(extracted)
        return "\n".join(parts)
    elif isinstance(val, dict):
        if "content" in val:
            return _extract_text_content(val["content"])
        if "text" in val:
            return _extract_text_content(val["text"])
        if "message" in val:
            return _extract_text_content(val["message"])
        return str(val)
    return str(val) if val is not None else ""


def load_otel_trace(
    file_path: Path, pricing: Dict[str, ModelPrice] = DEFAULT_PRICING
) -> OtelLoadResult:
    """Load and parse an OpenTelemetry trace JSON file following GenAI semantic conventions."""
    if not file_path.exists():
        raise FileNotFoundError(f"OTel trace file not found: {file_path}")

    try:
        content = file_path.read_text(encoding="utf-8")
        data = json.loads(content)
    except Exception as e:
        raise ValueError(f"Failed to parse OTel trace JSON file '{file_path.name}': {e}")

    raw_spans: List[dict] = []
    if isinstance(data, dict):
        for resource_span in data.get("resourceSpans", []):
            for scope_span in resource_span.get("scopeSpans", []):
                for span in scope_span.get("spans", []):
                    raw_spans.append(span)

    if not raw_spans:
        logger.warning(f"No spans found in OTel trace file '{file_path.name}'.")

    trace_ids = {s.get("traceId") for s in raw_spans if s.get("traceId")}
    if len(trace_ids) > 1:
        ids_str = ", ".join(sorted(trace_ids))
        raise ValueError(f"Trace file contains spans from multiple trace IDs: [{ids_str}]")

    trace_id = next(iter(trace_ids)) if trace_ids else "unknown_trace_id"

    def get_start_time(span: dict) -> int:
        val = span.get("startTimeUnixNano", 0)
        try:
            return int(val)
        except (ValueError, TypeError):
            return 0

    sorted_spans = sorted(raw_spans, key=get_start_time)

    executed_tools: List[ToolCall] = []
    triggered_skills: List[str] = []
    session_id: Optional[str] = None
    final_output_candidate: Optional[str] = None
    token_usage: List[TokenUsage] = []
    warnings: List[str] = []
    missing_args_warned = False

    for span in sorted_spans:
        attrs = _extract_span_attributes(span)
        op_name = attrs.get(otel_attrs.GEN_AI_OPERATION_NAME)

        # Check conversation ID on root/any span
        conv_id = attrs.get(otel_attrs.GEN_AI_CONVERSATION_ID)
        if conv_id and not session_id:
            session_id = str(conv_id)

        if op_name == otel_attrs.OPERATION_INVOKE_AGENT:
            agent_name = attrs.get(otel_attrs.GEN_AI_AGENT_NAME)
            if agent_name and agent_name not in triggered_skills:
                triggered_skills.append(str(agent_name))

        elif op_name == otel_attrs.OPERATION_EXECUTE_TOOL:
            tool_name = str(attrs.get(otel_attrs.GEN_AI_TOOL_NAME, "unknown_tool"))
            raw_args = attrs.get(otel_attrs.GEN_AI_TOOL_CALL_ARGUMENTS)

            tool_args: Dict[str, Any] = {}
            if raw_args:
                if isinstance(raw_args, dict):
                    tool_args = raw_args
                elif isinstance(raw_args, str):
                    try:
                        tool_args = json.loads(raw_args)
                    except Exception:
                        tool_args = {}
            else:
                if not missing_args_warned:
                    warnings.append(
                        "tool arguments not captured in trace; argument matching will be unreliable"
                    )
                    missing_args_warned = True

            executed_tools.append(ToolCall(tool_name=tool_name, args=tool_args))

        elif op_name == otel_attrs.OPERATION_CHAT:
            model = str(attrs.get(otel_attrs.GEN_AI_REQUEST_MODEL, "unknown_model"))
            in_tokens = attrs.get(otel_attrs.GEN_AI_USAGE_INPUT_TOKENS, 0)
            out_tokens = attrs.get(otel_attrs.GEN_AI_USAGE_OUTPUT_TOKENS, 0)
            token_usage.append(
                TokenUsage(model=model, input_tokens=int(in_tokens), output_tokens=int(out_tokens))
            )

            msg_content = attrs.get(otel_attrs.GEN_AI_OUTPUT_MESSAGES)
            if msg_content:
                final_output_candidate = _extract_text_content(msg_content)

    if not session_id:
        session_id = trace_id

    if final_output_candidate:
        final_output = final_output_candidate
    else:
        final_output = ""
        warnings.append("final output not captured in trace")

    cost_result = compute_cost(token_usage, pricing)
    cost_complete = not cost_result.unknown_models
    if not cost_complete:
        models_str = ", ".join(cost_result.unknown_models)
        warnings.append(f"no pricing for model(s) [{models_str}]; cost is incomplete")

    trace_model = AgentTrace(
        session_id=session_id,
        triggered_skills=triggered_skills,
        executed_tools=executed_tools,
        final_output=final_output,
        total_token_cost_usd=cost_result.total_usd,
        cost_complete=cost_complete,
    )

    return OtelLoadResult(trace=trace_model, token_usage=token_usage, warnings=warnings)
