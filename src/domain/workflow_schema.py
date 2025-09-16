from pydantic import BaseModel, Field
from typing import List, Dict, Any, Literal, Optional

class WorkflowInput(BaseModel):
    name: str
    type: Literal["text", "file", "json"]
    label: str
    default: Any = None

class StepParams(BaseModel):
    # Common
    output_key: Optional[str] = None
    input_mapping: Dict[str, str] = Field(default_factory=dict)
    
    # LLM, Code, API, Workflow steps
    prompt_template: Optional[str] = None
    function_name: Optional[str] = None
    workflow_name: Optional[str] = None
    output_mapping: Optional[Dict[str, str]] = None
    method: Optional[Literal["GET", "POST", "PUT", "DELETE"]] = None
    endpoint: Optional[str] = None
    headers: Optional[Dict[str, Any]] = None
    body: Optional[Dict[str, Any]] = None

    # --- NEW: Conditional Routing ---
    condition_key: Optional[str] = None
    routing_map: Optional[Dict[str, str]] = None

    # --- NEW: Dynamic Mapping ---
    map_input: Optional[str] = None

class WorkflowStep(BaseModel):
    name: str
    # --- NEW: Added 'conditional_router' ---
    type: Literal["llm", "code", "workflow", "api", "conditional_router"]
    dependencies: List[str] = Field(default_factory=list)
    params: StepParams

class WorkflowDefinition(BaseModel):
    name: str
    description: str
    inputs: List[WorkflowInput]
    steps: List[WorkflowStep]
    outputs: Optional[List[Any]] = None