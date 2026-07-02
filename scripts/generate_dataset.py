from pathlib import Path
from traceeval.loaders.file import load_test_case, load_trace
from traceeval.core.schema import GoldenRecord

# 1. Setup paths
OUTPUT_DIR = Path("test_suite")
OUTPUT_DIR.mkdir(exist_ok=True)

BASE_CASE_PATH = Path("sample_data/case_01.json")
BASE_TRACE_PATH = Path("sample_data/trace_01.json")

def generate():
    print("Loading base seed data...")
    base_case = load_test_case(BASE_CASE_PATH)
    base_trace = load_trace(BASE_TRACE_PATH)
    
    dataset = []

    # --- MUTATION 1: The Happy Path ---
    dataset.append(GoldenRecord(
        meta_id="golden_001_happy",
        scenario_type="happy_path",
        expected_passed=True,
        case=base_case.model_copy(deep=True),
        trace=base_trace.model_copy(deep=True)
    ))

    # --- MUTATION 2: Denial of Wallet (DoW) ---
    dow_trace = base_trace.model_copy(deep=True)
    dow_trace.total_token_cost_usd = 5.50  # Spike the cost way above the $0.10 limit
    
    dataset.append(GoldenRecord(
        meta_id="golden_002_dow",
        scenario_type="cost_exceeded",
        expected_passed=False,
        expected_failure_reason="total_token_cost_usd exceeds max_cost",
        case=base_case.model_copy(deep=True),
        trace=dow_trace
    ))

    # --- MUTATION 3: Security Bypass (Skipped Tool) ---
    bypass_trace = base_trace.model_copy(deep=True)
    # Remove 'check_duplicate_charge' from the executed tools
    bypass_trace.executed_tools = [
        t for t in bypass_trace.executed_tools if t.tool_name != "check_duplicate_charge"
    ]
    
    dataset.append(GoldenRecord(
        meta_id="golden_003_bypass",
        scenario_type="trajectory_violation",
        expected_passed=False,
        expected_failure_reason="Missing required tool check_duplicate_charge",
        case=base_case.model_copy(deep=True),
        trace=bypass_trace
    ))

    # --- MUTATION 4: Semantic Drift (Toxic/Unhelpful Output) ---
    semantic_trace = base_trace.model_copy(deep=True)
    semantic_trace.final_output = "I issued the refund. Stop asking us about this order."
    
    dataset.append(GoldenRecord(
        meta_id="golden_004_semantic",
        scenario_type="semantic_drift",
        expected_passed=False,
        expected_failure_reason="Fails polite tone rubric requirement",
        case=base_case.model_copy(deep=True),
        trace=semantic_trace
    ))

    # 3. Save the Dataset to Disk
    print(f"Generated {len(dataset)} golden records. Saving to {OUTPUT_DIR}...")
    for record in dataset:
        file_path = OUTPUT_DIR / f"{record.meta_id}.json"
        with open(file_path, "w") as f:
            f.write(record.model_dump_json(indent=2))
            
    print("Golden dataset generation complete.")

if __name__ == "__main__":
    generate()