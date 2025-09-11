from typing import Dict, Any, List, Optional
import json

class TurnContext:
    """
    A flexible data bus for the pipeline. It holds all data for a turn and
    also stores a rich debug log and metadata for visualization. It is mutated
    by each executor as the workflow progresses.
    """
    def __init__(self, **kwargs):
        self._data: Dict[str, Any] = kwargs
        self.execution_log: List[str] = []
        self.step_inputs: Dict[str, dict] = {}
        self.step_outputs: Dict[str, List[str]] = {}
        self.step_prompts: Dict[str, str] = {}
        self.log("TurnContext initialized.")

    def get(self, key: str, default: Any = None) -> Any:
        """Gets a value from the context's data dictionary."""
        # Handles dot notation for nested access, e.g., 'analysis_result.user_intent'
        if '.' in key:
            try:
                keys = key.split('.')
                value = self._data
                for k in keys:
                    value = value[k]
                return value
            except (KeyError, TypeError):
                return default
        return self._data.get(key, default)

    def set(self, key: str, value: Any):
        """Sets a value in the context's data dictionary."""
        # The orchestrator relies on keys being simple strings.
        # Dot notation is converted to underscores for top-level access.
        safe_key = key.replace('.', '_')
        self._data[safe_key] = value
        self.log(f"SET: Context key '{safe_key}' was added/updated.")

    def get_debug_log(self) -> List[str]:
        """Returns the full execution log."""
        return self.execution_log

    def log(self, message: str):
        """Adds a message to the execution log."""
        self.execution_log.append(message)

    def set_step_io(self, step_name: str, inputs: Dict[str, Any], outputs: List[str]):
        """Records the resolved inputs and declared outputs for a step."""
        self.step_inputs[step_name] = inputs
        self.step_outputs[step_name] = outputs

    def set_step_prompt(self, step_name: str, prompt: str):
        """Records the final constructed prompt for a step."""
        self.step_prompts[step_name] = prompt
    
    def resolve_inputs(self, mapping: dict) -> dict:
        """

        Resolves input mapping from the context's data dictionary.
        For each item in the mapping {placeholder: context_key}, it fetches
        the value from context_key and returns a new dict {placeholder: value}.
        It also handles JSON serialization for complex objects.
        """
        resolved = {}
        for placeholder, context_key in mapping.items():
            value = self.get(context_key)
            if isinstance(value, (dict, list, bool)):
                 resolved[placeholder] = json.dumps(value, indent=2)
            else:
                 resolved[placeholder] = value
        return resolved

    def to_dict(self) -> Dict[str, Any]:
        """Returns the core data dictionary for inspection."""
        return self._data