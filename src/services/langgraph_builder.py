import json
import yaml
import traceback
from typing import TypedDict, List, Dict, Any, Annotated, Set
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

def _resolve_value_from_state(state_data: Dict[str, Any], key_string: str) -> Any:
    if '.' in key_string:
        parent_key, child_key = key_string.split('.', 1)
        parent_value = state_data.get(parent_key)
        if isinstance(parent_value, dict):
            return parent_value.get(child_key)
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
            # Enforce fail-fast behavior: if an error is detected, halt execution of this node.
            if state.get("error_info"):
                return {}
            
            start_time = time.perf_counter()
            workflow_data = state.get("workflow_data", {})
            resolved_inputs = {key: _resolve_value_from_state(workflow_data, val) for key, val in params.get('input_mapping', {}).items()}
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
                return {"workflow_data": {output_key: response_json}, "debug_log": [debug_record]}
            except Exception as e:
                error_details = {"message": str(e), "traceback": traceback.format_exc()}
                debug_record = {"step_name": step_name, "type": "llm", "status": "Failed", "duration_ms": (time.perf_counter() - start_time) * 1000, "inputs": sanitized_inputs, "outputs": {}, "error": error_details}
                return {"debug_log": [debug_record], "error_info": [{"failed_step": step_name, **error_details}]}
        return llm_node

    def _create_code_node(self, step_name: str, params: Dict[str, Any]):
        async def code_node(state: GraphState) -> Dict[str, Any]:
            # Enforce fail-fast behavior: if an error is detected, halt execution of this node.
            if state.get("error_info"):
                return {}

            start_time = time.perf_counter()
            workflow_data = state.get("workflow_data", {})
            resolved_inputs = {
                model_field: _resolve_value_from_state(workflow_data, state_key)
                for model_field, state_key in params.get('input_mapping', {}).items()
            }
            sanitized_inputs = sanitize_for_json(resolved_inputs)
            try:
                StepClass = CODE_STEP_REGISTRY[params['function_name']]
                validated_input = StepClass.InputModel.model_validate(resolved_inputs)
                step_instance = StepClass(self.resources)
                output_model = await step_instance.execute(validated_input)
                result_data = output_model.model_dump()
                output_key = params['output_key']
                debug_record = {"step_name": step_name, "type": "code", "status": "Completed", "duration_ms": (time.perf_counter() - start_time) * 1000, "inputs": sanitized_inputs, "outputs": {output_key: result_data}}
                return {"workflow_data": {output_key: result_data}, "debug_log": [debug_record]}
            except Exception as e:
                error_details = {"message": str(e), "traceback": traceback.format_exc()}
                debug_record = {"step_name": step_name, "type": "code", "status": "Failed", "duration_ms": (time.perf_counter() - start_time) * 1000, "inputs": sanitized_inputs, "outputs": {}, "error": error_details}
                return {"debug_log": [debug_record], "error_info": [{"failed_step": step_name, **error_details}]}
        return code_node

    def _create_workflow_node(self, step_name: str, params: Dict[str, Any]):
        async def workflow_node(state: GraphState) -> Dict[str, Any]:
            # Enforce fail-fast behavior: if an error is detected, halt execution of this node.
            if state.get("error_info"):
                return {}

            start_time = time.perf_counter()
            workflow_data = state.get("workflow_data", {})
            sub_workflow_name = params['workflow_name']
            input_mapping = params.get('input_mapping', {})
            sub_initial_data = {
                sub_key: _resolve_value_from_state(workflow_data, parent_key) 
                for parent_key, sub_key in input_mapping.items()
            }
            sub_initial_state = {"workflow_data": sub_initial_data}
            sanitized_inputs = sanitize_for_json(sub_initial_state["workflow_data"])
            try:
                sub_graph = self._compile_sub_workflow(sub_workflow_name)
                sub_final_state = await sub_graph.ainvoke(sub_initial_state)
                if sub_final_state.get("error_info"):
                    raise RuntimeError(f"Sub-workflow '{sub_workflow_name}' failed.")

                output_mapping = params.get('output_mapping', {})
                sub_workflow_data = sub_final_state.get("workflow_data", {})
                parent_outputs = {parent_key: sub_workflow_data.get(sub_key) for sub_key, parent_key in output_mapping.items()}
                merged_debug_log = sub_final_state.get("debug_log", [])
                debug_record = {"step_name": step_name, "type": "workflow", "status": "Completed", "duration_ms": (time.perf_counter() - start_time) * 1000, "inputs": sanitized_inputs, "outputs": parent_outputs}
                return {"workflow_data": parent_outputs, "debug_log": [debug_record] + merged_debug_log}
            except Exception as e:
                error_details = {"message": str(e), "traceback": traceback.format_exc()}
                debug_record = {"step_name": step_name, "type": "workflow", "status": "Failed", "duration_ms": (time.perf_counter() - start_time) * 1000, "inputs": sanitized_inputs, "outputs": {}, "error": error_details}
                return {"debug_log": [debug_record], "error_info": [{"failed_step": step_name, **error_details}]}
        return workflow_node

    def build(self) -> Runnable:
        """
        Compiles the declarative YAML workflow into a LangGraph graph.
        This method constructs a static DAG, handling dependencies, fan-in joins,
        and terminal nodes to create a robust, race-condition-free graph.
        """
        steps = self.workflow_def.get('steps', [])
        all_step_names = {step['name'] for step in steps}
        
        # 1. Add all step nodes to the graph builder first.
        for step in steps:
            step_name = step['name']
            step_params = step.get('params', {})
            node_function = self._get_node_function(step_name, step_params)
            self.graph_builder.add_node(step_name, node_function)

        # 2. Identify all nodes that are used as dependencies.
        dependency_source_nodes = set()
        for step in steps:
            for dep in step.get('dependencies', []):
                if dep in self.output_to_step_map:
                    dependency_source_nodes.add(self.output_to_step_map[dep])

        # Terminal nodes are those that are never used as a dependency.
        terminal_nodes = all_step_names - dependency_source_nodes

        def create_conditional_function(target_step: str, required_deps: List[str]):
            def conditional_function(state: GraphState) -> str:
                workflow_data = state.get("workflow_data", {})
                if all(dep in workflow_data for dep in required_deps):
                    return target_step
                else:
                    return END
            return conditional_function

        # 3. Wire the graph by adding edges between nodes.
        for step in steps:
            step_name = step['name']
            dependencies = step.get('dependencies', [])

            # If a step has no dependencies, it's an entry point from START.
            if not dependencies:
                self.graph_builder.add_edge(START, step_name)
                continue

            parent_steps = {self.output_to_step_map[dep] for dep in dependencies if dep in self.output_to_step_map}

            # If a step has multiple parent dependencies, create a synchronization "join" node
            # with a conditional edge to ensure all parents have completed.
            if len(parent_steps) > 1:
                join_node_name = f"join_for_{step_name}"
                if join_node_name not in self.graph_builder.nodes:
                    # The join node is an empty function that just merges state.
                    self.graph_builder.add_node(join_node_name, lambda state: {})
                
                for parent_step in parent_steps:
                    self.graph_builder.add_edge(parent_step, join_node_name)
                
                conditional_func = create_conditional_function(step_name, dependencies)
                path_map = {step_name: step_name, END: END}
                self.graph_builder.add_conditional_edges(join_node_name, conditional_func, path_map)

            # For a single dependency, create a direct edge.
            elif len(parent_steps) == 1:
                parent_step = parent_steps.pop()
                self.graph_builder.add_edge(parent_step, step_name)

        # 4. Connect all identified terminal nodes to the END node.
        for node_name in terminal_nodes:
            self.graph_builder.add_edge(node_name, END)

        # 5. Compile the graph into a runnable object.
        return self.graph_builder.compile()

    def _get_node_function(self, step_name: str, step_params: Dict[str, Any]):
        step_type = self.steps_by_name[step_name]['type']
        if step_type == 'llm': return self._create_llm_node(step_name, step_params)
        if step_type == 'code': return self._create_code_node(step_name, step_params)
        if step_type == 'workflow': return self._create_workflow_node(step_name, step_params)
        raise ValueError(f"Unknown step type: {step_type}")