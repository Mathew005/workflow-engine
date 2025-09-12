import json
from typing import TypedDict, List, Dict, Any, Annotated, Optional
import operator
import inspect
import time

from langgraph.graph import StateGraph, START, END

from src.services.pipeline.resource_provider import ResourceProvider
from src.llm_integration.prompt_loader import load_prompt_template
from src.services.custom_code import CODE_STEP_REGISTRY

# --- ENHANCED STATE DEFINITION ---
# We add a new key, `debug_log`, to explicitly store structured debug information.
# It's an Annotated list, so each node can append its own record.
class GraphState(TypedDict):
    user_message: str
    session_id: str
    execution_log: Annotated[List[str], operator.add]
    
    # NEW: A structured log for verbose debugging
    debug_log: Annotated[List[Dict[str, Any]], operator.add]

    # All possible outputs from the workflow steps remain defined
    initial_analysis_result: Optional[Dict[str, Any]]
    validation_result: Optional[bool]
    user_profile: Optional[Dict[str, Any]]
    final_strategy: Optional[Dict[str, Any]]

class LangGraphBuilder:
    def __init__(self, workflow_definition: dict, resources: ResourceProvider):
        self.workflow_def = workflow_definition
        self.resources = resources
        self.graph_builder = StateGraph(GraphState)
        self.output_to_step_map = self._build_output_map()

    def _build_output_map(self) -> Dict[str, str]:
        return {
            step['params']['output_key']: step['name']
            for step in self.workflow_def.get('steps', [])
            if 'params' in step and 'output_key' in step.get('params', {})
        }

    # --- NODE FACTORIES NOW INSTRUMENTED FOR DEBUGGING ---

    def _create_llm_node(self, step_name: str, params: Dict[str, Any]):
        async def llm_node(state: GraphState) -> Dict[str, Any]:
            start_time = time.perf_counter()
            log_msg = f"Executing LLM node '{step_name}'."
            
            # 1. Capture Inputs
            resolved_inputs = {
                key: state.get(val) for key, val in params['input_mapping'].items()
            }
            
            # Prepare inputs for the prompt template (which needs strings)
            prompt_inputs = {
                key: json.dumps(val, indent=2) if isinstance(val, (dict, list)) else val
                for key, val in resolved_inputs.items()
            }
            
            prompt = load_prompt_template(params['prompt_template'], prompt_inputs)
            result = await self.resources.get_gemini_client().call_gemini_async(prompt, step_name)
            
            # 2. Capture Outputs
            response_json = result.get('response_json', {})
            output_key = params['output_key']
            
            end_time = time.perf_counter()
            duration_ms = (end_time - start_time) * 1000

            # 3. Create Structured Debug Record
            debug_record = {
                "step_name": step_name,
                "type": "llm",
                "inputs": resolved_inputs,
                "outputs": {output_key: response_json},
                "duration_ms": duration_ms
            }

            return {
                output_key: response_json,
                "execution_log": [log_msg],
                "debug_log": [debug_record] # Append the record to our new log
            }
        return llm_node

    def _create_code_node(self, step_name: str, params: Dict[str, Any]):
        async def code_node(state: GraphState) -> Dict[str, Any]:
            start_time = time.perf_counter()
            log_msg = f"Executing code node '{step_name}'."
            
            # 1. Capture Inputs
            input_key = params['input_key']
            input_data = state.get(input_key)
            
            if input_data is None:
                raise ValueError(f"Node '{step_name}' received None for required input '{input_key}'.")
            
            func = CODE_STEP_REGISTRY[params['function_name']]
            result = await func(input_data) if inspect.iscoroutinefunction(func) else func(input_data)
            
            # 2. Capture Outputs
            output_key = params['output_key']
            
            end_time = time.perf_counter()
            duration_ms = (end_time - start_time) * 1000

            # 3. Create Structured Debug Record
            debug_record = {
                "step_name": step_name,
                "type": "code",
                "inputs": {input_key: input_data},
                "outputs": {output_key: result},
                "duration_ms": duration_ms
            }

            return {
                output_key: result,
                "execution_log": [log_msg],
                "debug_log": [debug_record] # Append the record
            }
        return code_node

    def build(self):
        # This build logic remains the same as the last correct version
        steps = self.workflow_def.get('steps', [])
        all_step_names = {step['name'] for step in steps}
        non_terminal_nodes = set()

        for step in steps:
            node_func = self._create_llm_node(step['name'], step['params']) if step['type'] == 'llm' else self._create_code_node(step['name'], step['params'])
            self.graph_builder.add_node(step['name'], node_func)

        for step in steps:
            step_name = step['name']
            dependencies = step.get('dependencies', [])
            if not dependencies:
                self.graph_builder.add_edge(START, step_name)
            else:
                for dep_key in dependencies:
                    source_step_name = self.output_to_step_map.get(dep_key)
                    if not source_step_name:
                        raise ValueError(f"Unresolved dependency '{dep_key}' for step '{step_name}'")
                    self.graph_builder.add_edge(source_step_name, step_name)
                    non_terminal_nodes.add(source_step_name)
        
        terminal_nodes = all_step_names - non_terminal_nodes
        for node_name in terminal_nodes:
             self.graph_builder.add_edge(node_name, END)
        
        return self.graph_builder.compile()