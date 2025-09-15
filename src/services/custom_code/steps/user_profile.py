from pydantic import BaseModel
from typing import Dict, Any

from src.services.custom_code.base import BaseCustomStep

class GetUserProfileByIntentInput(BaseModel):
    analysis_result: Dict[str, Any]

class GetUserProfileByIntentOutput(BaseModel):
    profile: Dict[str, Any]

class GetUserProfileByIntentStep(BaseCustomStep):
    InputModel = GetUserProfileByIntentInput
    OutputModel = GetUserProfileByIntentOutput

    async def execute(self, input_data: GetUserProfileByIntentInput) -> GetUserProfileByIntentOutput:
        """Simulates fetching user data based on LLM analysis."""
        intent = input_data.analysis_result.get('user_intent', 'UNKNOWN')
        print(f"[CUSTOM CODE] Fetching user profile for intent: {intent}")
        
        if intent == "ELABORATE":
            profile_data = {"user_id": "user-123", "tier": "premium", "preferences": ["details", "tech_specs"]}
        else:
            profile_data = {"user_id": "user-123", "tier": "standard", "preferences": ["summary"]}
        
        return GetUserProfileByIntentOutput(profile=profile_data)