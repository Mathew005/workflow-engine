from pydantic import BaseModel
from typing import Dict, Any

from src.services.custom_code.base import BaseCustomStep

class GetValueFromDictInput(BaseModel):
    data: Dict[str, Any]
    key: str = "company_name" # Default the key for convenience

class GetValueFromDictOutput(BaseModel):
    value: str

class GetValueFromDictStep(BaseCustomStep):
    """
    A simple utility step to extract a specific key's value from a dictionary.
    This acts as a "shim" to connect services that expect different input shapes.
    """
    InputModel = GetValueFromDictInput
    OutputModel = GetValueFromDictOutput

    async def execute(self, input_data: GetValueFromDictInput) -> GetValueFromDictOutput:
        print(f"[CUSTOM CODE] Extracting key '{input_data.key}' from dictionary.")
        
        extracted_value = input_data.data.get(input_data.key)
        if not extracted_value or not isinstance(extracted_value, str):
            # Handle cases where the company name wasn't found
            return GetValueFromDictOutput(value="Unknown")

        return GetValueFromDictOutput(value=extracted_value)