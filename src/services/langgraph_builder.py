import json
import yaml
import traceback
import httpx
import time
import re
from typing import TypedDict, List, Dict, Any, Annotated, Set, Callable, Awaitable
import operator
from pathlib import Path

from functools import wraps

from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import Runnable

from src.services.pipeline.resource_provider import ResourceProvider
from src.llm_integration.prompt_loader import load_prompt_template
from src.custom_code import CODE_STEP_REGISTRY

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

def _resolve_value_from_state(state_data: Dict[str, Any], key_string: str) -> Any:
    if '.' in key_string:
        parent_key, child_key = key_string.split('.', 1)
        parent_value = state_data.get(parent_key)
        if isinstance(parent_value, dict):
            return _resolve_value_from_state(parent_value, child_key)
        return None
    if key_string.startswith("'") and key_string.endswith("'"):
        return key_string[1:-1]
    return state_data.get(key_string)

class LangGraphBuilder:
    def __init__(self, workflow_definition: dict, resources: ResourceProvider, workflow_path: Path):
        self.workflow_def = workflow_definition
        self.resources = resources
        self.workflow_package_path = workflow_path.parent 
        self.graph_builder = StateGraph(GraphState)
        self.output_to_step_map = self._build_output_map()
        self.steps_by_name = {step['name']: step for step in self.workflow_def.get('steps', [])}

    def _resolve_placeholders(self, data_structure: Any, state_data: Dict[str, Any]) -> Any:
        # ... (implementation is unchanged)
        if isinstance(data_structure, dict):
            return {k: self._resolve_placeholders(v, state_data) for k, v in data_structure.items()}
        if isinstance(data_structure, list):
            return [self._resolve_placeholders(v, state_data) for v in data_structure]
        if isinstance(data_structure, str):
            for match in re.finditer(r'<([^>]+)>', data_structure):
                placeholder = match.group(1)
                resolved_value = _resolve_value_from_state(state_data, placeholder)
                if data_structure == f"<{placeholder}>":
                    return resolved_value
                data_structure = data_structure.replace(f"<{placeholder}>", str(resolved_value))
        return data_structure
    
    def _build_output_map(self) -> Dict[str, str]:
        # ... (implementation is unchanged)
        output_map = {}
        for step in self.workflow_def.get('steps', []):
            params = step.get('params', {})
            if params.get('output_key'): output_map[params['output_key']] = step['name']
            if step['type'] == 'workflow' and params.get('output_mapping'):
                for out_key in params['output_mapping'].values(): output_map[out_key] = step['name']
        return output_map

    def _compile_sub_workflow(self, name: str) -> Runnable:
        """
        Finds and compiles a sub-workflow. It now correctly looks for
        other workflow packages within the main 'workflows' directory.
        """
        if name in COMPILED_WORKFLOW_CACHE:
            return COMPILED_WORKFLOW_CACHE[name]
        
        # --- THIS IS THE FIX ---
        # The base path for all workflows is the parent directory of the current workflow package.
        # e.g., if current is 'src/workflows/orchestrator', the parent is 'src/workflows'.
        workflows_base_dir = self.workflow_package_path.parent
        sub_workflow_path = workflows_base_dir / name / "workflow.yaml"

        if not sub_workflow_path.exists():
            raise FileNotFoundError(f"Sub-workflow package '{name}' not found. Searched at: {sub_workflow_path}")
        
        with open(sub_workflow_path, 'r') as f:
            sub_workflow_dict = yaml.safe_load(f)
            # Pass the correct path for the sub-workflow's context
            builder = LangGraphBuilder(sub_workflow_dict, self.resources, sub_workflow_path)
            compiled_graph = builder.build()
            COMPILED_WORKFLOW_CACHE[name] = compiled_graph
            return compiled_graph


    # --- REFACTOR: Centralized Node Executor Wrapper ---
    def _node_wrapper(
        self,
        step_name: str,
        step_type: str,
        params: Dict[str, Any],
        logic_func: Callable[[GraphState], Awaitable[tuple[Dict[str, Any], Dict[str, Any]]]]
    ) -> Callable[[GraphState], Awaitable[Dict[str, Any]]]:
        """
        A decorator-like function that wraps the core logic of each node type.
        It handles all common boilerplate: error checking, timing, exception handling,
        and formatting the debug log and final state dictionary.
        """
        async def wrapped_node(state: GraphState) -> Dict[str, Any]:
            if state.get("error_info"):
                return {}
            
            start_time = time.perf_counter()
            sanitized_inputs, outputs, additional_logs = {}, {}, []
            
            try:
                # Execute the unique logic for the node
                outputs, sanitized_inputs, additional_logs = await logic_func(state)
                
                # Format success record
                debug_record = {
                    "step_name": step_name, "type": step_type, "status": "Completed",
                    "duration_ms": (time.perf_counter() - start_time) * 1000,
                    "inputs": sanitized_inputs, "outputs": outputs
                }
                return {"workflow_data": outputs, "debug_log": [debug_record] + additional_logs}

            except Exception as e:
                # Format failure record
                error_details = {"message": str(e), "traceback": traceback.format_exc()}
                debug_record = {
                    "step_name": step_name, "type": step_type, "status": "Failed",
                    "duration_ms": (time.perf_counter() - start_time) * 1000,
                    "inputs": sanitized_inputs, "outputs": {}, "error": error_details
                }
                return {"debug_log": [debug_record], "error_info": [{"failed_step": step_name, **error_details}]}
        
        return wrapped_node

    def _create_llm_node(self, step_name: str, params: Dict[str, Any]):
        async def _llm_logic(state: GraphState) -> tuple[Dict[str, Any], Dict[str, Any], list]:
            workflow_data = state.get("workflow_data", {})
            resolved_inputs = {p: _resolve_value_from_state(workflow_data, sk) for p, sk in params.get('input_mapping', {}).items()}
            sanitized_inputs = sanitize_for_json(resolved_inputs)
            
            prompt_content, p_inputs = [], {}
            for key, value in resolved_inputs.items():
                if isinstance(value, dict) and 'mime_type' in value and 'data' in value: prompt_content.append(value)
                else: p_inputs[key] = json.dumps(value, indent=2) if isinstance(value, (dict, list)) else value
            
            text_prompt = load_prompt_template(params['prompt_template'], p_inputs, self.workflow_package_path)
            prompt_content.insert(0, text_prompt)
            
            result = await self.resources.get_gemini_client().call_gemini_async(prompt_content, step_name)
            response_json = result.get('response_json', {})
            output_key = params['output_key']
            
            return {output_key: response_json}, sanitized_inputs, []
            
        return self._node_wrapper(step_name, "llm", params, _llm_logic)

    def _create_code_node(self, step_name: str, params: Dict[str, Any]):
        async def _code_logic(state: GraphState) -> tuple[Dict[str, Any], Dict[str, Any], list]:
            workflow_data = state.get("workflow_data", {})
            resolved_inputs = {mf: _resolve_value_from_state(workflow_data, sk) for mf, sk in params.get('input_mapping', {}).items()}
            sanitized_inputs = sanitize_for_json(resolved_inputs)
            
            StepClass = CODE_STEP_REGISTRY[params['function_name']]
            validated_input = StepClass.InputModel.model_validate(resolved_inputs)
            step_instance = StepClass(self.resources)
            output_model = await step_instance.execute(validated_input)
            result_data = output_model.model_dump()
            output_key = params['output_key']
            
            return {output_key: result_data}, sanitized_inputs, []

        return self._node_wrapper(step_name, "code", params, _code_logic)

    def _create_api_node(self, step_name: str, params: Dict[str, Any]):
        async def _api_logic(state: GraphState) -> tuple[Dict[str, Any], Dict[str, Any], list]:
            workflow_data = state.get("workflow_data", {})
            resolved_endpoint = self._resolve_placeholders(params.get('endpoint', ''), workflow_data)
            resolved_headers = self._resolve_placeholders(params.get('headers', {}), workflow_data)
            resolved_body = self._resolve_placeholders(params.get('body', {}), workflow_data)
            method = params.get('method', 'GET').upper()
            sanitized_inputs = sanitize_for_json({"method": method, "endpoint": resolved_endpoint, "headers": resolved_headers, "body": resolved_body})

            async with httpx.AsyncClient() as client:
                response = await client.request(method=method, url=resolved_endpoint, headers=resolved_headers, json=resolved_body if method in ["POST", "PUT"] else None)
                response.raise_for_status()
                response_json = response.json()
            
            output_key = params['output_key']
            return {output_key: response_json}, sanitized_inputs, []
            
        return self._node_wrapper(step_name, "api", params, _api_logic)

    def _create_workflow_node(self, step_name: str, params: Dict[str, Any]):
        async def _workflow_logic(state: GraphState) -> tuple[Dict[str, Any], Dict[str, Any], list]:
            workflow_data = state.get("workflow_data", {})
            sub_workflow_name = params['workflow_name']
            input_mapping = params.get('input_mapping', {})
            sub_initial_data = {sub_key: _resolve_value_from_state(workflow_data, parent_key) for parent_key, sub_key in input_mapping.items()}
            sub_initial_state = {"workflow_data": sub_initial_data}
            sanitized_inputs = sanitize_for_json(sub_initial_state["workflow_data"])
            
            sub_graph = self._compile_sub_workflow(sub_workflow_name)
            
            async for event in sub_graph.astream_events(sub_initial_state, version="v1"):
                repackaged_event = {"parent_step": step_name, "sub_workflow": sub_workflow_name, "original_event": event}
                await self.resources.emit_event({"type": "sub_workflow_event", "data": repackaged_event})
            
            final_sub_state = await sub_graph.ainvoke(sub_initial_state)
            
            if final_sub_state.get("error_info"):
                sub_error = final_sub_state["error_info"][0]
                raise RuntimeError(f"Sub-workflow '{sub_workflow_name}' failed at step '{sub_error.get('failed_step')}': {sub_error.get('message')}")
            
            output_mapping = params.get('output_mapping', {})
            sub_workflow_data = final_sub_state.get("workflow_data", {})
            parent_outputs = {parent_key: sub_workflow_data.get(sub_key) for sub_key, parent_key in output_mapping.items()}
            
            # Sub-workflows can have their own logs, which we pass along
            additional_logs = final_sub_state.get("debug_log", [])
            
            return parent_outputs, sanitized_inputs, additional_logs

        return self._node_wrapper(step_name, "workflow", params, _workflow_logic)

    def build(self) -> Runnable:
        # ... (implementation is unchanged)
        steps = self.workflow_def.get('steps', [])
        all_step_names = {step['name'] for step in steps}
        for step in steps:
            step_name = step['name']
            step_params = step.get('params', {})
            node_function = self._get_node_function(step_name, step_params)
            self.graph_builder.add_node(step_name, node_function)
        dependency_source_nodes = set()
        for step in steps:
            for dep in step.get('dependencies', []):
                if dep in self.output_to_step_map:
                    dependency_source_nodes.add(self.output_to_step_map[dep])
        terminal_nodes = all_step_names - dependency_source_nodes
        def create_conditional_function(target_step: str, required_deps: List[str]):
            def conditional_function(state: GraphState) -> str:
                workflow_data = state.get("workflow_data", {})
                if all(dep in workflow_data for dep in required_deps):
                    return target_step
                else:
                    return END
            return conditional_function
        for step in steps:
            step_name = step['name']
            dependencies = step.get('dependencies', [])
            if not dependencies:
                self.graph_builder.add_edge(START, step_name)
                continue
            parent_steps = {self.output_to_step_map[dep] for dep in dependencies if dep in self.output_to_step_map}
            if len(parent_steps) > 1:
                join_node_name = f"join_for_{step_name}"
                if join_node_name not in self.graph_builder.nodes:
                    self.graph_builder.add_node(join_node_name, lambda state: {})
                for parent_step in parent_steps:
                    self.graph_builder.add_edge(parent_step, join_node_name)
                conditional_func = create_conditional_function(step_name, dependencies)
                path_map = {step_name: step_name, END: END}
                self.graph_builder.add_conditional_edges(join_node_name, conditional_func, path_map)
            elif len(parent_steps) == 1:
                parent_step = parent_steps.pop()
                self.graph_builder.add_edge(parent_step, step_name)
        for node_name in terminal_nodes:
            self.graph_builder.add_edge(node_name, END)
        return self.graph_builder.compile()

    def _get_node_function(self, step_name: str, step_params: Dict[str, Any]):
        step_type = self.steps_by_name[step_name]['type']
        if step_type == 'llm': return self._create_llm_node(step_name, step_params)
        if step_type == 'code': return self._create_code_node(step_name, step_params)
        if step_type == 'workflow': return self._create_workflow_node(step_name, step_params)
        if step_type == 'api': return self._create_api_node(step_name, step_params)
        raise ValueError(f"Unknown step type: {step_type}")