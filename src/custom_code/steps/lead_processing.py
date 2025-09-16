from pydantic import BaseModel, Field
from typing import Dict, Any
import random

from src.custom_code.base import BaseCustomStep

# --- Step A ---
class ValidateEmailInput(BaseModel):
    email: str

class ValidateEmailOutput(BaseModel):
    is_valid: bool
    domain: str

class ValidateEmailStep(BaseCustomStep):
    """Simulates checking if an email is valid and deliverable."""
    InputModel = ValidateEmailInput
    OutputModel = ValidateEmailOutput

    async def execute(self, input_data: ValidateEmailInput) -> ValidateEmailOutput:
        # In a real app, this would use a service like NeverBounce
        is_valid = "@" in input_data.email and "." in input_data.email.split("@")[-1]
        domain = input_data.email.split("@")[-1] if is_valid else "unknown"
        return ValidateEmailOutput(is_valid=is_valid, domain=domain)

# --- Step B ---
class EnrichCompanyInput(BaseModel):
    company_name: str

class EnrichCompanyOutput(BaseModel):
    employee_count: int
    industry: str

class EnrichCompanyStep(BaseCustomStep):
    """Simulates a Clearbit API call to get firmographic data."""
    InputModel = EnrichCompanyInput
    OutputModel = EnrichCompanyOutput

    async def execute(self, input_data: EnrichCompanyInput) -> EnrichCompanyOutput:
        return EnrichCompanyOutput(
            employee_count=random.randint(10, 10000),
            industry=random.choice(["SaaS", "Healthcare", "Finance", "Manufacturing"])
        )

# --- Step 2 ---
class ScoreLeadInput(BaseModel):
    validation_result: Dict[str, Any]
    company_data: Dict[str, Any]
    competitor_analysis: Dict[str, Any]

class ScoreLeadOutput(BaseModel):
    lead_score: int = Field(..., ge=0, le=100)

class ScoreLeadStep(BaseCustomStep):
    """Applies business logic to calculate a lead score."""
    InputModel = ScoreLeadInput
    OutputModel = ScoreLeadOutput

    async def execute(self, input_data: ScoreLeadInput) -> ScoreLeadOutput:
        score = 50 # Start with a baseline score
        if not input_data.validation_result.get("is_valid", False): return ScoreLeadOutput(lead_score=0)
        
        # Adjust score based on industry and size
        if input_data.company_data.get("industry") in ["SaaS", "Finance"]: score += 20
        if input_data.company_data.get("employee_count", 0) > 1000: score += 15

        # Penalize if it's a competitor
        if input_data.competitor_analysis.get("is_competitor", False): score -= 30

        return ScoreLeadOutput(lead_score=max(0, min(100, score)))

# --- Step 3 ---
class DetermineRoutingInput(BaseModel):
    score_result: Dict[str, Any]
    original_intent: str

class DetermineRoutingOutput(BaseModel):
    team: str
    priority: str

class DetermineRoutingStep(BaseCustomStep):
    """Uses the lead score and intent to determine the final routing."""
    InputModel = DetermineRoutingInput
    OutputModel = DetermineRoutingOutput

    async def execute(self, input_data: DetermineRoutingInput) -> DetermineRoutingOutput:
        score = input_data.score_result.get("lead_score", 0)

        if input_data.original_intent == "Technical Question":
            return DetermineRoutingOutput(team="Support Tier 1", priority="Medium")

        if score > 80:
            return DetermineRoutingOutput(team="Senior Sales", priority="Critical")
        elif score > 60:
            return DetermineRoutingOutput(team="Sales Associates", priority="High")
        else:
            return DetermineRoutingOutput(team="Lead Nurturing", priority="Low")