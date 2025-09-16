from pydantic import BaseModel, Field
from typing import List, Dict, Any

from src.custom_code.base import BaseCustomStep

class ValidateTitleInput(BaseModel):
    title: str

class ValidateTitleOutput(BaseModel):
    is_valid: bool
    char_count: int

class ValidateTitleStep(BaseCustomStep):
    """Checks if a title meets a minimum character length."""
    InputModel = ValidateTitleInput
    OutputModel = ValidateTitleOutput

    async def execute(self, input_data: ValidateTitleInput) -> ValidateTitleOutput:
        length = len(input_data.title)
        return ValidateTitleOutput(is_valid=length >= 10, char_count=length)

class CalculateAverageLengthInput(BaseModel):
    articles: List[Dict[str, Any]] # Expects a list of objects, e.g., [{"length": 50}, {"length": 150}]

class CalculateAverageLengthOutput(BaseModel):
    average_length: float
    decision: str = Field(..., description="Either 'short' or 'long'")

class CalculateAverageLengthStep(BaseCustomStep):
    """Calculates the average length from a list of article stats and makes a decision."""
    InputModel = CalculateAverageLengthInput
    OutputModel = CalculateAverageLengthOutput

    async def execute(self, input_data: CalculateAverageLengthInput) -> CalculateAverageLengthOutput:
        if not input_data.articles:
            return CalculateAverageLengthOutput(average_length=0, decision='short')
        
        total_length = sum(article.get('length', 0) for article in input_data.articles)
        average = total_length / len(input_data.articles)
        
        decision = 'long' if average >= 100 else 'short'
        
        return CalculateAverageLengthOutput(average_length=round(average, 2), decision=decision)