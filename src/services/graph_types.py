import re
import operator
from typing import TypedDict, List, Dict, Any, Annotated

# --- SHARED TYPE DEFINITIONS ---

def merge_workflow_data(left: dict, right: dict) -> dict:
    """Merges two dictionaries, concatenating list values."""
    return {**left, **right}

class GraphState(TypedDict):
    """The central state representation for all workflows."""
    execution_log: Annotated[List[str], operator.add]
    debug_log: Annotated[List[Dict[str, Any]], operator.add]
    error_info: Annotated[List[Dict[str, Any]], operator.add]
    workflow_data: Annotated[dict, merge_workflow_data]

# --- SHARED HELPER FUNCTIONS ---

def sanitize_for_json(data: Any) -> Any:
    """Recursively sanitizes data to be JSON-serializable."""
    if isinstance(data, dict): return {k: sanitize_for_json(v) for k, v in data.items()}
    if isinstance(data, list): return [sanitize_for_json(v) for v in data]
    if isinstance(data, bytes): return f"<bytes of length {len(data)}>"
    return data

def _resolve_value_from_state(state_data: Dict[str, Any], key_string: str) -> Any:
    """Recursively fetches a value from a nested dictionary using a dot-separated key string."""
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

def _resolve_placeholders(data_structure: Any, state_data: Dict[str, Any]) -> Any:
    """Recursively finds and replaces <placeholder> strings in a data structure."""
    if isinstance(data_structure, dict): return {k: _resolve_placeholders(v, state_data) for k, v in data_structure.items()}
    if isinstance(data_structure, list): return [_resolve_placeholders(v, state_data) for v in data_structure]
    if isinstance(data_structure, str):
        for match in re.finditer(r'<([^>]+)>', data_structure):
            placeholder = match.group(1); resolved_value = _resolve_value_from_state(state_data, placeholder)
            if data_structure == f"<{placeholder}>": return resolved_value
            data_structure = data_structure.replace(f"<{placeholder}>", str(resolved_value))
    return data_structure