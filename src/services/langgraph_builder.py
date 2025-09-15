import json
import yaml
import traceback
from typing import TypedDict, List, Dict, Any, Annotated
import operator
import time
from pathlib import Path

from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import Runnable

from src.services.pipeline.resource_provider import ResourceProvider
from src.llm_integration.prompt_loader import load_prompt_template
from src.services.custom_code import CODE_STEP_REGISTRY

COMPILED_WORKFLOW_CACHE: Dict[str, Runnable] = {}

def merge_workflow_data(left: dict, right: dict) -> dict:
    return {**left, **right}

class GraphState(TypedDict):
    execution_log: Annotated[List[str], operator.add]
    debug_log: Annotated[List[Dict[str, Any]], operator.add]
    error_info: Annotated[List[Dict[str, Any]], operator.add]
    workflow_data: Annotated[dict, merge_workflow_data]

def sanitize_for_json(data: Any) -> Any:
    if isinstance(data, dict): return {k: sanitize_for_json(v) for k, v in data.items()}
    if isinstance(data, list): return [sanitize_for_json(v) for v in data]
    if isinstance(data, bytes): return f"<bytes of length {len(data)}>"
    return data

class LangGraphBuilder:
    def __init__(self, workflow_definition: dict, resources: ResourceProvider, workflow_path: Path):
        self.workflow_def = workflow_definition
        self.resources = resources
        self.workflow_package_path = workflow_path.parent 
        self.graph_builder = StateGraph(GraphState)
        self.output_to_step_map = self._build_output_map()

    def _build_output_map(self) -> Dict[str, str]:
        output_map = {}
        for step in self.workflow_def.get('steps', []):
            params = step.get('params', {})
            if params.get('output_key'): output_map[params['output_key']] = step['name']
            if step['type'] == 'workflow' and params.get('output_mapping'):
                for out_key in params['output_mapping'].values(): output_map[out_key] = step['name']
        return output_map

    def _compile_sub_workflow(self, name: str) -> Runnable:
        if name in COMPILED_WORKFLOW_CACHE: return COMPILED_WORKFLOW_CACHE[name]
        sub_workflow_path = self.workflow_package_path.parent / name / "workflow.yaml"
        if not sub_workflow_path.exists(): raise FileNotFoundError(f"Sub-workflow package '{name}' not found: {sub_workflow_path}")
        with open(sub_workflow_path, 'r') as f:
            sub_workflow_dict = yaml.safe_load(f)
            builder = LangGraphBuilder(sub_workflow_dict, self.resources, sub_workflow_path)
            compiled_graph = builder.build()
            COMPILED_WORKFLOW_CACHE[name] = compiled_graph
            return compiled_graph

    def _create_llm_node(self, step_name: str, params: Dict[str, Any]):
        async def llm_node(state: GraphState) -> Dict[str, Any]:
            start_time = time.perf_counter()
            workflow_data = state.get("workflow_data", {})
            resolved_inputs = {key: workflow_data.get(val) for key, val in params.get('input_mapping', {}).items()}
            sanitized_inputs = sanitize_for_json(resolved_inputs)
            try:
                prompt_content, p_inputs = [], {}
                for key, value in resolved_inputs.items():
                    if isinstance(value, dict) and 'mime_type' in value and 'data' in value: prompt_content.append(value)
                    else: p_inputs[key] = json.dumps(value, indent=2) if isinstance(value, (dict, list)) else value
                text_prompt = load_prompt_template(params['prompt_template'], p_inputs, self.workflow_package_path)
                prompt_content.insert(0, text_prompt)
                result = await self.resources.get_gemini_client().call_gemini_async(prompt_content, step_name)
                response_json, output_key = result.get('response_json', {}), params['output_key']
                debug_record = {"step_name": step_name, "type": "llm", "status": "Completed", "duration_ms": (time.perf_counter() - start_time) * 1000, "inputs": sanitized_inputs, "outputs": {output_key: response_json}}
                return {"workflow_data": {output_key: response_json}, "debug_log": [debug_record], "error_info": []}
            except Exception as e:
                error_details = {"message": str(e), "traceback": traceback.format_exc()}
                debug_record = {"step_name": step_name, "type": "llm", "status": "Failed", "duration_ms": (time.perf_counter() - start_time) * 1000, "inputs": sanitized_inputs, "outputs": {}, "error": error_details}
                return {"debug_log": [debug_record], "error_info": [{"failed_step": step_name, **error_details}]}
        return llm_node

    def _create_code_node(self, step_name: str, params: Dict[str, Any]):
        async def code_node(state: GraphState) -> Dict[str, Any]:
            start_time = time.perf_counter()
            workflow_data = state.get("workflow_data", {})
            input_key, raw_input_data = params['input_key'], workflow_data.get(params['input_key'])
            sanitized_inputs = sanitize_for_json({input_key: raw_input_data})
            try:
                StepClass = CODE_STEP_REGISTRY[params['function_name']]
                if raw_input_data is None: raise ValueError(f"Input '{input_key}' was None.")
                
                primary_input_field_name = list(StepClass.InputModel.model_fields.keys())[0]
                input_data_for_model = {primary_input_field_name: raw_input_data}
                validated_input = StepClass.InputModel.model_validate(input_data_for_model)
                
                step_instance = StepClass(self.resources)
                output_model = await step_instance.execute(validated_input)
                
                # --- FIX: The definitive output handling logic ---
                output_fields = list(output_model.model_fields.keys())
                # If the OutputModel has exactly one field, extract its value directly.
                if len(output_fields) == 1:
                    result_data = getattr(output_model, output_fields[0])
                # Otherwise, return the full dictionary representation of the model.
                else:
                    result_data = output_model.model_dump()

                output_key = params['output_key']
                debug_record = {"step_name": step_name, "type": "code", "status": "Completed", "duration_ms": (time.perf_counter() - start_time) * 1000, "inputs": sanitized_inputs, "outputs": {output_key: result_data}}
                return {"workflow_data": {output_key: result_data}, "debug_log": [debug_record], "error_info": []}
            except Exception as e:
                error_details = {"message": str(e), "traceback": traceback.format_exc()}
                debug_record = {"step_name": step_name, "type": "code", "status": "Failed", "duration_ms": (time.perf_counter() - start_time) * 1000, "inputs": sanitized_inputs, "outputs": {}, "error": error_details}
                return {"debug_log": [debug_record], "error_info": [{"failed_step": step_name, **error_details}]}
        return code_node

    def _create_workflow_node(self, step_name: str, params: Dict[str, Any]):
        async def workflow_node(state: GraphState) -> Dict[str, Any]:
            start_time = time.perf_counter()
            workflow_data = state.get("workflow_data", {})
            sub_workflow_name = params['workflow_name']
            input_mapping = params.get('input_mapping', {})
            sub_initial_state = {"workflow_data": {sub_key: workflow_data.get(parent_key) for parent_key, sub_key in input_mapping.items()}}
            sanitized_inputs = sanitize_for_json(sub_initial_state["workflow_data"])
            try:
                sub_graph = self._compile_sub_workflow(sub_workflow_name)
                sub_final_state = await sub_graph.ainvoke(sub_initial_state)
                if sub_final_state.get("error_info"):
                    failed_step = sub_final_state['error_info'][0].get('failed_step', 'Unknown')
                    error_msg = sub_final_state['error_info'][0].get('message', 'No message')
                    raise RuntimeError(f"Sub-workflow '{sub_workflow_name}' failed at step '{failed_step}': {error_msg}")

                output_mapping = params.get('output_mapping', {})
                sub_workflow_data = sub_final_state.get("workflow_data", {})
                parent_outputs = {parent_key: sub_workflow_data.get(sub_key) for sub_key, parent_key in output_mapping.items()}
                merged_debug_log = sub_final_state.get("debug_log", [])
                debug_record = {"step_name": step_name, "type": "workflow", "status": "Completed", "duration_ms": (time.perf_counter() - start_time) * 1000, "inputs": sanitized_inputs, "outputs": parent_outputs}
                return {"workflow_data": parent_outputs, "debug_log": [debug_record] + merged_debug_log, "error_info": []}
            except Exception as e:
                error_details = {"message": str(e), "traceback": traceback.format_exc()}
                debug_record = {"step_name": step_name, "type": "workflow", "status": "Failed", "duration_ms": (time.perf_counter() - start_time) * 1000, "inputs": sanitized_inputs, "outputs": {}, "error": error_details}
                return {"debug_log": [debug_record], "error_info": [{"failed_step": step_name, **error_details}]}
        return workflow_node

    def build(self) -> Runnable:
        # This build logic is correct and does not need to change.
        steps = self.workflow_def.get('steps', [])
        for step in steps:
            node_func = self._get_node_function(step)
            self.graph_builder.add_node(step['name'], node_func)
        for step in steps:
            step_name, dependencies = step['name'], step.get('dependencies', [])
            source_nodes = [self.output_to_step_map[dep_key] for dep_key in dependencies if dep_key in self.output_to_step_map]
            if not source_nodes: self.graph_builder.add_edge(START, step_name)
            else: self.graph_builder.add_edge(source_nodes, step_name)
        
        def should_halt(state: GraphState) -> str:
            return END if state.get("error_info") else "continue"
        
        all_step_names = {step['name'] for step in steps}
        all_source_nodes = {source for step in steps for source in [self.output_to_step_map.get(d) for d in step.get('dependencies', [])] if source}
        terminal_nodes = all_step_names - all_source_nodes

        if terminal_nodes:
            self.graph_builder.add_node("halt_checker", lambda state: {})
            for node in terminal_nodes:
                self.graph_builder.add_edge(node, "halt_checker")
            self.graph_builder.add_conditional_edges("halt_checker", should_halt, {"continue": END, END: END})
        
        return self.graph_builder.compile()

    def _get_node_function(self, step: Dict[str, Any]):
        step_type = step['type']
        if step_type == 'llm': return self._create_llm_node(step['name'], step['params'])
        if step_type == 'code': return self._create_code_node(step['name'], step['params'])
        if step_type == 'workflow': return self._create_workflow_node(step['name'], step['params'])
        raise ValueError(f"Unknown step type: {step_type}")