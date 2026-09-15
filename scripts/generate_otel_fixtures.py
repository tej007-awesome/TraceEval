import json
import time
from pathlib import Path

from google.protobuf.json_format import MessageToDict
from opentelemetry.exporter.otlp.proto.common._internal.trace_encoder import encode_spans
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

FIXTURES_DIR = Path("tests/fixtures/otel")


def generate_trace_data(include_content: bool = True) -> dict:
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("traceeval.reference_agent")

    with tracer.start_as_current_span("invoke_agent refund-processor") as root:
        root.set_attribute("gen_ai.operation.name", "invoke_agent")
        root.set_attribute("gen_ai.agent.name", "refund-processor")
        root.set_attribute("gen_ai.conversation.id", "sess_otel_001")
        time.sleep(0.002)

        # Step 1: LLM initial decision
        with tracer.start_as_current_span("chat gpt-4o-mini") as chat1:
            chat1.set_attribute("gen_ai.operation.name", "chat")
            chat1.set_attribute("gen_ai.request.model", "gpt-4o-mini")
            chat1.set_attribute("gen_ai.usage.input_tokens", 150)
            chat1.set_attribute("gen_ai.usage.output_tokens", 30)
            time.sleep(0.002)

        # Step 2: Tool call 1 (lookup_order)
        with tracer.start_as_current_span("execute_tool lookup_order") as tool1:
            tool1.set_attribute("gen_ai.operation.name", "execute_tool")
            tool1.set_attribute("gen_ai.tool.name", "lookup_order")
            tool1.set_attribute("gen_ai.tool.call.id", "call_lookup_001")
            if include_content:
                tool1.set_attribute(
                    "gen_ai.tool.call.arguments", json.dumps({"order_id": "4521"})
                )
            time.sleep(0.002)

        # Step 3: LLM reasoning after lookup
        with tracer.start_as_current_span("chat gpt-4o-mini") as chat2:
            chat2.set_attribute("gen_ai.operation.name", "chat")
            chat2.set_attribute("gen_ai.request.model", "gpt-4o-mini")
            chat2.set_attribute("gen_ai.usage.input_tokens", 220)
            chat2.set_attribute("gen_ai.usage.output_tokens", 35)
            time.sleep(0.002)

        # Step 4: Tool call 2 (check_duplicate_charge)
        with tracer.start_as_current_span("execute_tool check_duplicate_charge") as tool2:
            tool2.set_attribute("gen_ai.operation.name", "execute_tool")
            tool2.set_attribute("gen_ai.tool.name", "check_duplicate_charge")
            tool2.set_attribute("gen_ai.tool.call.id", "call_check_dup_002")
            if include_content:
                tool2.set_attribute(
                    "gen_ai.tool.call.arguments", json.dumps({"order_id": "4521"})
                )
            time.sleep(0.002)

        # Step 5: LLM reasoning after check
        with tracer.start_as_current_span("chat gpt-4o-mini") as chat3:
            chat3.set_attribute("gen_ai.operation.name", "chat")
            chat3.set_attribute("gen_ai.request.model", "gpt-4o-mini")
            chat3.set_attribute("gen_ai.usage.input_tokens", 310)
            chat3.set_attribute("gen_ai.usage.output_tokens", 40)
            time.sleep(0.002)

        # Step 6: Tool call 3 (issue_refund)
        with tracer.start_as_current_span("execute_tool issue_refund") as tool3:
            tool3.set_attribute("gen_ai.operation.name", "execute_tool")
            tool3.set_attribute("gen_ai.tool.name", "issue_refund")
            tool3.set_attribute("gen_ai.tool.call.id", "call_refund_003")
            if include_content:
                tool3.set_attribute(
                    "gen_ai.tool.call.arguments",
                    json.dumps({"order_id": "4521", "amount": "full"}),
                )
            time.sleep(0.002)

        # Step 7: Final response chat
        with tracer.start_as_current_span("chat gpt-4o-mini") as chat4:
            chat4.set_attribute("gen_ai.operation.name", "chat")
            chat4.set_attribute("gen_ai.request.model", "gpt-4o-mini")
            chat4.set_attribute("gen_ai.usage.input_tokens", 420)
            chat4.set_attribute("gen_ai.usage.output_tokens", 55)
            if include_content:
                chat4.set_attribute(
                    "gen_ai.output.messages",
                    "I have verified the duplicate charge for order #4521. A full refund has been issued.",
                )
            time.sleep(0.002)

    spans = sorted(exporter.get_finished_spans(), key=lambda s: s.start_time)
    pb_request = encode_spans(spans)
    return MessageToDict(pb_request)


def generate_fixtures():
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    happy_data = generate_trace_data(include_content=True)
    happy_path = FIXTURES_DIR / "refund_happy.json"
    with open(happy_path, "w", encoding="utf-8") as f:
        json.dump(happy_data, f, indent=2)
    print(f"Generated {happy_path}")

    no_args_data = generate_trace_data(include_content=False)
    no_args_path = FIXTURES_DIR / "refund_no_args.json"
    with open(no_args_path, "w", encoding="utf-8") as f:
        json.dump(no_args_data, f, indent=2)
    print(f"Generated {no_args_path}")


if __name__ == "__main__":
    generate_fixtures()
