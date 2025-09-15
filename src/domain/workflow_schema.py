from pydantic import BaseModel, Field
from typing import List, Dict, Any, Literal, Optional

class WorkflowInput(BaseModel):
    name: str
    type: Literal["text", "file"]
    label: str
    default: Any = None

class StepParams(BaseModel):
    # Common
    output_key: Optional[str] = None # Not required for workflow steps
    
    # Used by 'llm' and 'code' steps
    input_mapping: Dict[str, str] = Field(default_factory=dict)
    
    # LLM steps
    prompt_template: Optional[str] = None
    
    # Code steps
    function_name: Optional[str] = None
    
    # Workflow steps
    workflow_name: Optional[str] = None
    output_mapping: Optional[Dict[str, str]] = None

class WorkflowStep(BaseModel):
    name: str
    type: Literal["llm", "code", "workflow"] # <-- ADD "workflow"
    dependencies: List[str] = Field(default_factory=list)
    params: StepParams

class WorkflowDefinition(BaseModel):
    name: str
    description: str
    inputs: List[WorkflowInput]
    steps: List[WorkflowStep]