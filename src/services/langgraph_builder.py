import json
import yaml
import traceback
import httpx
import time
import re
import asyncio
from typing import TypedDict, List, Dict, Any, Annotated, Callable, Awaitable, Optional
import operator
from pathlib import Path

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
    if key_string == "item": return state_data.get("item")
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
        if isinstance(data_structure, dict): return {k: self._resolve_placeholders(v, state_data) for k, v in data_structure.items()}
        if isinstance(data_structure, list): return [self._resolve_placeholders(v, state_data) for v in data_structure]
        if isinstance(data_structure, str):
            for match in re.finditer(r'<([^>]+)>', data_structure):
                placeholder = match.group(1); resolved_value = _resolve_value_from_state(state_data, placeholder)
                if data_structure == f"<{placeholder}>": return resolved_value
                data_structure = data_structure.replace(f"<{placeholder}>", str(resolved_value))
        return data_structure
    
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
        if not sub_workflow_path.exists(): raise FileNotFoundError(f"Sub-workflow package '{name}' not found at: {sub_workflow_path}")
        with open(sub_workflow_path, 'r') as f:
            sub_workflow_dict = yaml.safe_load(f)
            builder = LangGraphBuilder(sub_workflow_dict, self.resources, sub_workflow_path)
            compiled_graph = builder.build()
            COMPILED_WORKFLOW_CACHE[name] = compiled_graph
            return compiled_graph

    def _node_wrapper(self, step_name: str, step_type: str, params: Dict[str, Any], logic_func: Callable[[GraphState, Optional[Any], Optional[int]], Awaitable[tuple[Dict, Dict, list]]]):
        async def wrapped_node(state: GraphState) -> Dict[str, Any]:
            if state.get("error_info"): return {}
            start_time = time.perf_counter(); outputs, additional_logs, sanitized_inputs = {}, [], {}
            try:
                map_input_key = params.get("map_input")
                workflow_data = state.get("workflow_data", {})
                if map_input_key:
                    items_to_process = _resolve_value_from_state(workflow_data, map_input_key)
                    if not isinstance(items_to_process, list): raise TypeError(f"Map input '{map_input_key}' must resolve to a list.")
                    tasks = [logic_func(state, item, i) for i, item in enumerate(items_to_process)]
                    results = await asyncio.gather(*tasks)
                    outputs = {params['output_key']: [res[0] for res in results]}
                    sanitized_inputs = { "map_source": map_input_key, "item_count": len(items_to_process) }
                else:
                    outputs, sanitized_inputs, additional_logs = await logic_func(state, None, None)
                debug_record = {"step_name": step_name, "type": step_type, "status": "Completed", "duration_ms": (time.perf_counter() - start_time) * 1000, "inputs": sanitized_inputs, "outputs": outputs}
                return {"workflow_data": outputs, "debug_log": [debug_record] + additional_logs}
            except Exception as e:
                # --- FIX: Ensure sanitized_inputs is captured even on early failure ---
                if not sanitized_inputs and 'logic_func' in locals():
                    try:
                        # Attempt to get inputs for logging even if logic failed
                        _, sanitized_inputs, _ = await logic_func(state, None, None)
                    except Exception:
                        sanitized_inputs = {"error": "Could not resolve inputs before failure."}
                error_details = {"message": str(e), "traceback": traceback.format_exc()}
                debug_record = {"step_name": step_name, "type": step_type, "status": "Failed", "duration_ms": (time.perf_counter() - start_time) * 1000, "inputs": sanitized_inputs, "outputs": {}, "error": error_details}
                return {"debug_log": [debug_record], "error_info": [{"failed_step": step_name, **error_details}]}
        return wrapped_node

    def _create_llm_node(self, step_name: str, params: Dict[str, Any]):
        async def _llm_logic(state: GraphState, item: Optional[Any], index: Optional[int]) -> tuple[Dict, Dict, list]:
            context_data = {**state.get("workflow_data", {}), "item": item} if item is not None else state.get("workflow_data", {})
            resolved_inputs = {p: _resolve_value_from_state(context_data, sk) for p, sk in params.get('input_mapping', {}).items()}
            sanitized_inputs = sanitize_for_json(resolved_inputs)
            if all(v is None for v in resolved_inputs.values()): raise ValueError("All resolved inputs are None. Check your input_mapping and workflow state.")
            prompt_content, p_inputs = [], {}
            for key, value in resolved_inputs.items():
                if isinstance(value, dict) and 'mime_type' in value and 'data' in value: prompt_content.append(value)
                else: p_inputs[key] = json.dumps(value, indent=2) if isinstance(value, (dict, list)) else value
            text_prompt = load_prompt_template(params['prompt_template'], p_inputs, self.workflow_package_path)
            prompt_content.insert(0, text_prompt)
            result = await self.resources.get_gemini_client().call_gemini_async(prompt_content, step_name)
            output = result.get('response_json', {})
            return (output, sanitized_inputs, []) if item is not None else ({params['output_key']: output}, sanitized_inputs, [])
        return self._node_wrapper(step_name, "llm", params, _llm_logic)

    def _create_code_node(self, step_name: str, params: Dict[str, Any]):
        async def _code_logic(state: GraphState, item: Optional[Any], index: Optional[int]) -> tuple[Dict, Dict, list]:
            context_data = {**state.get("workflow_data", {}), "item": item} if item is not None else state.get("workflow_data", {})
            resolved_inputs = {mf: _resolve_value_from_state(context_data, sk) for mf, sk in params.get('input_mapping', {}).items()}
            sanitized_inputs = sanitize_for_json(resolved_inputs)
            StepClass = CODE_STEP_REGISTRY[params['function_name']]
            validated_input = StepClass.InputModel.model_validate(resolved_inputs)
            step_instance = StepClass(self.resources)
            output_model = await step_instance.execute(validated_input)
            output = output_model.model_dump()
            return (output, sanitized_inputs, []) if item is not None else ({params['output_key']: output}, sanitized_inputs, [])
        return self._node_wrapper(step_name, "code", params, _code_logic)

    def _create_api_node(self, step_name: str, params: Dict[str, Any]):
        async def _api_logic(state: GraphState, item: Optional[Any], index: Optional[int]) -> tuple[Dict, Dict, list]:
            context_data = {**state.get("workflow_data", {}), "item": item} if item is not None else state.get("workflow_data", {})
            resolved_endpoint = self._resolve_placeholders(params.get('endpoint', ''), context_data)
            resolved_headers = self._resolve_placeholders(params.get('headers', {}), context_data)
            resolved_body = self._resolve_placeholders(params.get('body', {}), context_data)
            method = params.get('method', 'GET').upper()
            sanitized_inputs = sanitize_for_json({"method": method, "endpoint": resolved_endpoint, "headers": resolved_headers, "body": resolved_body})
            async with httpx.AsyncClient() as client:
                response = await client.request(method=method, url=resolved_endpoint, headers=resolved_headers, json=resolved_body if method in ["POST", "PUT"] else None)
                response.raise_for_status()
                output = response.json()
            return (output, sanitized_inputs, []) if item is not None else ({params['output_key']: output}, sanitized_inputs, [])
        return self._node_wrapper(step_name, "api", params, _api_logic)

    def _create_workflow_node(self, step_name: str, params: Dict[str, Any]):
        async def _workflow_logic(state: GraphState, item: Optional[Any], index: Optional[int]) -> tuple[Dict, Dict, list]:
            context_data = {**state.get("workflow_data", {}), "item": item} if item is not None else state.get("workflow_data", {})
            sub_workflow_name = params['workflow_name']
            input_mapping = params.get('input_mapping', {})
            sub_initial_data = {sub_key: _resolve_value_from_state(context_data, parent_key) for parent_key, sub_key in input_mapping.items()}
            sub_initial_state = {"workflow_data": sub_initial_data}
            sanitized_inputs = sanitize_for_json(sub_initial_state["workflow_data"])
            sub_graph = self._compile_sub_workflow(sub_workflow_name)
            async for event in sub_graph.astream_events(sub_initial_state, version="v1"):
                repackaged_event = {"parent_step": step_name, "sub_workflow": sub_workflow_name, "original_event": event, "map_index": index}
                await self.resources.emit_event({"type": "sub_workflow_event", "data": repackaged_event})
            final_sub_state = await sub_graph.ainvoke(sub_initial_state)
            if final_sub_state.get("error_info"):
                sub_error = final_sub_state["error_info"][0]
                raise RuntimeError(f"Sub-workflow '{sub_workflow_name}' failed at step '{sub_error.get('failed_step')}': {sub_error.get('message')}")
            output_mapping = params.get('output_mapping', {})
            sub_workflow_data = final_sub_state.get("workflow_data", {})
            parent_outputs = {parent_key: sub_workflow_data.get(sub_key) for sub_key, parent_key in output_mapping.items()}
            additional_logs = final_sub_state.get("debug_log", [])
            return (parent_outputs, sanitized_inputs, additional_logs)
        return self._node_wrapper(step_name, "workflow", params, _workflow_logic)

    def build(self) -> Runnable:
        steps = self.workflow_def.get('steps', [])
        for step in steps:
            step_name, step_type, step_params = step['name'], step['type'], step.get('params', {})
            if step_type == 'conditional_router': self.graph_builder.add_node(step_name, lambda state: state)
            else: self.graph_builder.add_node(step_name, self._get_node_function(step_name, step_params))

        # --- FIX: Correctly identify router targets to prevent incorrect edge creation ---
        router_targets = set()
        for step in steps:
            if step['type'] == 'conditional_router':
                for target_node in step.get('params', {}).get('routing_map', {}).values():
                    router_targets.add(target_node)
        
        for step in steps:
            step_name, step_type, dependencies = step['name'], step['type'], step.get('dependencies', [])
            
            if not dependencies:
                # --- FIX: Only connect to START if it's not a target of a router ---
                if step_name not in router_targets:
                    self.graph_builder.add_edge(START, step_name)
            else:
                source_nodes = {self.output_to_step_map[dep] for dep in dependencies if dep in self.output_to_step_map}
                for source in source_nodes:
                    self.graph_builder.add_edge(source, step_name)

            if step_type == 'conditional_router':
                params = step.get('params', {}); condition_key, routing_map = params['condition_key'], params['routing_map']
                def create_conditional_func(key: str):
                    def conditional_func(state: GraphState):
                        value = _resolve_value_from_state(state.get("workflow_data", {}), key)
                        return str(value)
                    return conditional_func
                self.graph_builder.add_conditional_edges(step_name, create_conditional_func(condition_key), routing_map)

        all_step_names = {s['name'] for s in steps}; dependency_sources = set()
        for step in steps:
            for dep in step.get('dependencies', []):
                if dep in self.output_to_step_map: dependency_sources.add(self.output_to_step_map[dep])
        for step in steps:
            if step['type'] == 'conditional_router':
                dependency_sources.add(step['name']) # The router itself is a dependency source for its targets
                for target_node in step.get('params', {}).get('routing_map', {}).values():
                    if target_node in all_step_names: dependency_sources.add(target_node)
        
        terminal_nodes = all_step_names - dependency_sources
        for node in terminal_nodes:
            if self.steps_by_name[node]['type'] != 'conditional_router': self.graph_builder.add_edge(node, END)
        
        return self.graph_builder.compile()

    def _get_node_function(self, step_name: str, step_params: Dict[str, Any]):
        step_type = self.steps_by_name[step_name]['type']
        if step_type == 'llm': return self._create_llm_node(step_name, step_params)
        if step_type == 'code': return self._create_code_node(step_name, step_params)
        # --- FIX: Fully implemented and uncommented ---
        if step_type == 'api': return self._create_api_node(step_name, step_params)
        if step_type == 'workflow': return self._create_workflow_node(step_name, step_params)
        raise ValueError(f"Unknown step type: {step_type}")