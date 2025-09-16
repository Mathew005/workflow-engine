import json
import httpx
import yaml
from typing import Dict, Any

from .pipeline.resource_provider import ResourceProvider
from src.llm_integration.prompt_loader import load_prompt_template
from src.custom_code import CODE_STEP_REGISTRY
from .graph_types import _resolve_value_from_state, _resolve_placeholders

# Note: The 'index' parameter is reserved for future use with sub-workflow mapping.
async def _llm_logic(resources: ResourceProvider, workflow_package_path, step_name: str, params: Dict[str, Any], context_data: Dict[str, Any]) -> tuple[Dict, Dict, list]:
    resolved_inputs = {p: _resolve_value_from_state(context_data, sk) for p, sk in params.get('input_mapping', {}).items()}
    if all(v is None for v in resolved_inputs.values()): raise ValueError("All resolved inputs for LLM node are None.")
    prompt_content, p_inputs = [], {}
    for key, value in resolved_inputs.items():
        if isinstance(value, dict) and 'mime_type' in value and 'data' in value: prompt_content.append(value)
        else: p_inputs[key] = json.dumps(value, indent=2) if isinstance(value, (dict, list)) else value
    text_prompt = load_prompt_template(params['prompt_template'], p_inputs, workflow_package_path)
    prompt_content.insert(0, text_prompt)
    result = await resources.get_gemini_client().call_gemini_async(prompt_content, step_name)
    output = result.get('response_json', {})
    return output, resolved_inputs, []

async def _code_logic(resources: ResourceProvider, workflow_package_path, step_name: str, params: Dict[str, Any], context_data: Dict[str, Any]) -> tuple[Dict, Dict, list]:
    resolved_inputs = {mf: _resolve_value_from_state(context_data, sk) for mf, sk in params.get('input_mapping', {}).items()}
    StepClass = CODE_STEP_REGISTRY[params['function_name']]
    validated_input = StepClass.InputModel.model_validate(resolved_inputs)
    step_instance = StepClass(resources)
    output_model = await step_instance.execute(validated_input)
    output = output_model.model_dump()
    return output, resolved_inputs, []

async def _api_logic(resources: ResourceProvider, workflow_package_path, step_name: str, params: Dict[str, Any], context_data: Dict[str, Any]) -> tuple[Dict, Dict, list]:
    resolved_endpoint = _resolve_placeholders(params.get('endpoint', ''), context_data)
    resolved_headers = _resolve_placeholders(params.get('headers', {}), context_data)
    resolved_body = _resolve_placeholders(params.get('body', {}), context_data)
    method = params.get('method', 'GET').upper()
    async with httpx.AsyncClient() as client:
        response = await client.request(method=method, url=resolved_endpoint, headers=resolved_headers, json=resolved_body if method in ["POST", "PUT"] else None)
        response.raise_for_status()
        output = response.json()
    return output, {"method": method, "endpoint": resolved_endpoint, "headers": resolved_headers, "body": resolved_body}, []

async def _workflow_logic(resources: ResourceProvider, workflow_package_path, step_name: str, params: Dict[str, Any], context_data: Dict[str, Any]) -> tuple[Dict, Dict, list]:
    from .langgraph_builder import LangGraphBuilder, COMPILED_WORKFLOW_CACHE # Local import to avoid top-level circular dependency
    sub_workflow_name = params['workflow_name']
    input_mapping = params.get('input_mapping', {})
    sub_initial_data = {sub_key: _resolve_value_from_state(context_data, parent_key) for parent_key, sub_key in input_mapping.items()}
    sub_initial_state = {"workflow_data": sub_initial_data}
    
    if sub_workflow_name in COMPILED_WORKFLOW_CACHE:
        sub_graph = COMPILED_WORKFLOW_CACHE[sub_workflow_name]
    else:
        sub_workflow_path = workflow_package_path.parent / sub_workflow_name / "workflow.yaml"
        if not sub_workflow_path.exists(): raise FileNotFoundError(f"Sub-workflow package '{sub_workflow_name}' not found at: {sub_workflow_path}")
        with open(sub_workflow_path, 'r') as f: sub_workflow_dict = yaml.safe_load(f)
        builder = LangGraphBuilder(sub_workflow_dict, resources, sub_workflow_path)
        sub_graph = builder.build()
        COMPILED_WORKFLOW_CACHE[sub_workflow_name] = sub_graph
    
    map_index = context_data.get("map_index")
    async for event in sub_graph.astream_events(sub_initial_state, version="v1"):
        await resources.emit_event({"type": "sub_workflow_event", "data": {"parent_step": step_name, "sub_workflow": sub_workflow_name, "original_event": event, "map_index": map_index}})
    
    final_sub_state = await sub_graph.ainvoke(sub_initial_state)
    if final_sub_state.get("error_info"):
        sub_error = final_sub_state["error_info"][0]
        raise RuntimeError(f"Sub-workflow '{sub_workflow_name}' failed at step '{sub_error.get('failed_step')}': {sub_error.get('message')}")
    
    output_mapping = params.get('output_mapping', {})
    sub_workflow_data = final_sub_state.get("workflow_data", {})
    parent_outputs = {parent_key: sub_workflow_data.get(sub_key) for sub_key, parent_key in output_mapping.items()}
    additional_logs = final_sub_state.get("debug_log", [])
    return parent_outputs, sub_initial_data, additional_logs