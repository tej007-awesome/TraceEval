import sys
import importlib
from pathlib import Path
from agentci.core.schema import EDDTestCase, AgentTrace

def run_live_pipeline(pipeline_path: str, case: EDDTestCase) -> AgentTrace:
    """
    Dynamically imports an agent function and runs it with the test case input.
    Format expected: 'module.submodule:function_name'
    """
    # Ensure the current working directory is in the path so we can import local modules
    sys.path.insert(0, str(Path.cwd()))
    
    if ":" not in pipeline_path:
        raise ValueError("Pipeline path must be in 'module:function' format (e.g., examples.agent:run).")
    
    module_path, fn_name = pipeline_path.split(":", 1)
    
    try:
        module = importlib.import_module(module_path)
        agent_fn = getattr(module, fn_name)
    except ImportError as e:
        raise ImportError(f"Could not import module '{module_path}': {e}")
    except AttributeError:
        raise AttributeError(f"Function '{fn_name}' not found in module '{module_path}'.")
    
    # Execute the live agent
    trace = agent_fn(case.input_prompt)
    
    if not isinstance(trace, AgentTrace):
        raise TypeError(f"Pipeline must return an AgentTrace, got {type(trace)} instead.")
        
    return trace