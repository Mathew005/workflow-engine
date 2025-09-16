from pydantic import BaseModel, Field
import re

from src.custom_code.base import BaseCustomStep

class GetTextStatsInput(BaseModel):
    text: str

class GetTextStatsOutput(BaseModel):
    word_count: int
    char_count: int

class GetTextStatsStep(BaseCustomStep):
    """Calculates basic statistics for a block of text."""
    InputModel = GetTextStatsInput
    OutputModel = GetTextStatsOutput

    async def execute(self, input_data: GetTextStatsInput) -> GetTextStatsOutput:
        words = re.findall(r'\b\w+\b', input_data.text)
        return GetTextStatsOutput(word_count=len(words), char_count=len(input_data.text))