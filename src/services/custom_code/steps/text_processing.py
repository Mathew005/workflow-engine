from pydantic import BaseModel, Field
from typing import Dict, Any
import re

from src.services.custom_code.base import BaseCustomStep

class CheckTextQualityInput(BaseModel):
    text: str

class CheckTextQualityOutput(BaseModel):
    word_count: int
    # A simple metric for complexity
    average_word_length: float = Field(..., description="Average length of words in the text.")

class CheckTextQualityStep(BaseCustomStep):
    """Calculates basic quality statistics for a given block of text."""
    InputModel = CheckTextQualityInput
    OutputModel = CheckTextQualityOutput

    async def execute(self, input_data: CheckTextQualityInput) -> CheckTextQualityOutput:
        words = re.findall(r'\b\w+\b', input_data.text.lower())
        word_count = len(words)
        
        if word_count == 0:
            return CheckTextQualityOutput(word_count=0, average_word_length=0)

        total_word_length = sum(len(word) for word in words)
        avg_length = total_word_length / word_count
        
        return CheckTextQualityOutput(
            word_count=word_count,
            average_word_length=round(avg_length, 2)
        )