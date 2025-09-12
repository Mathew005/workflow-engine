
from typing import List, Optional
from pydantic import BaseModel, Field

# This file is now much simpler. The complex TurnContext is gone.
# We only keep Pydantic models for validating data structures,
# especially the outputs from LLM calls.

class MentionedTopic(BaseModel):
    id: Optional[str] = None
    name: str
    is_emergent: bool

class AnalysisResult(BaseModel):
    user_intent: str
    user_style: str
    mentioned_topics: List[MentionedTopic] = Field(default_factory=list)

class MemoryNode(BaseModel):
    fact: str
    source: str