import time
import traceback
from typing import Dict, Any, Optional, Callable

from .graph_types import GraphState, sanitize_for_json
from .node_logic import _llm_logic, _code_logic, _api_logic, _workflow_logic

def _node_wrapper(step_name: str, step_type: str, params: Dict[str, Any], logic_func: Callable):
    async def wrapped_node(state: GraphState) -> Dict[str, Any]:
        if state.get("error_info"): return {}
        start_time = time.perf_counter()
        outputs, additional_logs, sanitized_inputs = {}, [], {}
        try:
            map_input_key = params.get("map_input")
            workflow_data = state.get("workflow_data", {})
            
            if map_input_key:
                from .graph_types import _resolve_value_from_state
                import asyncio
                items_to_process = _resolve_value_from_state(workflow_data, map_input_key)
                if not isinstance(items_to_process, list): raise TypeError(f"Map input '{map_input_key}' must resolve to a list.")
                
                async def run_logic_for_item(item, index):
                    context = {**workflow_data, "item": item, "map_index": index}
                    return await logic_func(item=item, context_data=context)
                
                results_with_details = await asyncio.gather(*(run_logic_for_item(item, i) for i, item in enumerate(items_to_process)))

                detailed_records, aggregated_outputs = [], []
                for i, (output, inputs, logs) in enumerate(results_with_details):
                    detailed_records.append({"step_name": f"{step_name} [Run {i+1}/{len(items_to_process)}]", "type": f"mapped_{step_type}", "status": "Completed", "duration_ms": 0, "inputs": inputs, "outputs": output, "is_child": True})
                    aggregated_outputs.append(output); additional_logs.extend(logs)
                
                outputs = {params['output_key']: aggregated_outputs}
                sanitized_inputs = {"map_source": map_input_key, "item_count": len(items_to_process)}
                additional_logs.extend(detailed_records)
            else:
                output, resolved_inputs, additional_logs = await logic_func(item=None, context_data=workflow_data)
                outputs = {params['output_key']: output} if params.get('output_key') else output
                sanitized_inputs = sanitize_for_json(resolved_inputs)

            debug_record = {"step_name": step_name, "type": step_type, "status": "Completed", "duration_ms": (time.perf_counter() - start_time) * 1000, "inputs": sanitized_inputs, "outputs": outputs}
            return {"workflow_data": outputs, "debug_log": [debug_record] + additional_logs}
        except Exception as e:
            error_details = {"message": str(e), "traceback": traceback.format_exc()}
            debug_record = {"step_name": step_name, "type": step_type, "status": "Failed", "duration_ms": (time.perf_counter() - start_time) * 1000, "inputs": sanitized_inputs or {"error": "Could not resolve inputs before failure."}, "outputs": {}, "error": error_details}
            return {"debug_log": [debug_record], "error_info": [{"failed_step": step_name, **error_details}]}
    return wrapped_node

def create_node_function(resources, workflow_package_path, step_name, step_type, params):
    logic_map = {
        'llm': _llm_logic, 'code': _code_logic,
        'api': _api_logic, 'workflow': _workflow_logic
    }
    if step_type not in logic_map:
        raise ValueError(f"Unknown step type: {step_type}")

    async def logic_caller(item: Optional[Any], context_data: Dict[str, Any]):
        return await logic_map[step_type](resources, workflow_package_path, step_name, params, context_data)
        
    return _node_wrapper(step_name, step_type, params, logic_caller)