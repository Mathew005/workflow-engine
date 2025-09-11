from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

class TurnContext:
    """
    A flexible data bus for the pipeline. Acts like a dictionary and also
    stores a rich debug log of operations performed during the turn.
    """
    def __init__(self, **kwargs):
        self._data: Dict[str, Any] = kwargs
        self._debug_log: List[str] = []
        self.step_inputs: Dict[str, List[str]] = {}
        self.step_outputs: Dict[str, List[str]] = {}
        self.step_prompts: Dict[str, str] = {}
        self.log("TurnContext initialized.")

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any):
        self._data[key] = value
        self.log(f"SET: Key '{key}' was added/updated.")
    
    def set_step_io(self, step_name: str, inputs: List[str], outputs: List[str]):
        self.step_inputs[step_name] = inputs
        self.step_outputs[step_name] = outputs

    def set_step_prompt(self, step_name: str, prompt: str):
        self.step_prompts[step_name] = prompt

    def log(self, message: str):
        self._debug_log.append(message)

    def get_debug_log(self) -> List[str]:
        return self._debug_log
    
    def to_dict(self) -> Dict[str, Any]:
        return self._data

# Models for data produced by steps
class AnalysisResult(BaseModel):
    user_intent: str
    user_style: str
    mentioned_topics: List[dict] = Field(default_factory=list)

class MemoryNode(BaseModel):
    fact: str
    source: str