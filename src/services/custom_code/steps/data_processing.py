from pydantic import BaseModel
from typing import Dict, Any

from src.services.custom_code.base import BaseCustomStep

class ExtractKeyFromDictInput(BaseModel):
    data: Dict[str, Any]

class ExtractKeyFromDictOutput(BaseModel):
    result: str

class ExtractKeyFromDictStep(BaseCustomStep):
    InputModel = ExtractKeyFromDictInput
    OutputModel = ExtractKeyFromDictOutput

    async def execute(self, input_data: ExtractKeyFromDictInput) -> ExtractKeyFromDictOutput:
        """Extracts the 'answer' key from a dictionary, with a fallback."""
        print(f"[CUSTOM CODE] Extracting 'answer' from: {input_data.data}")
        answer = input_data.data.get("answer", "No answer was found in the dictionary.")
        return ExtractKeyFromDictOutput(result=answer)