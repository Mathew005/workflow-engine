from pydantic import BaseModel, Field
from typing import List, Dict, Any, Literal, Optional

class WorkflowInput(BaseModel):
    name: str
    type: Literal["text", "file"]
    label: str
    default: Any = None

class StepParams(BaseModel):
    output_key: str
    input_mapping: Dict[str, str] = Field(default_factory=dict)
    input_key: Optional[str] = None
    function_name: Optional[str] = None
    prompt_template: Optional[str] = None

class WorkflowStep(BaseModel):
    name: str
    type: Literal["llm", "code"] # 'workflow' type will be added in a later phase
    dependencies: List[str] = Field(default_factory=list)
    params: StepParams

class WorkflowDefinition(BaseModel):
    name: str
    description: str
    inputs: List[WorkflowInput]
    steps: List[WorkflowStep]