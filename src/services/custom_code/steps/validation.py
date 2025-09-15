from pydantic import BaseModel

from src.services.custom_code.base import BaseCustomStep

class IsMessageLongEnoughInput(BaseModel):
    message: str

class IsMessageLongEnoughOutput(BaseModel):
    is_long_enough: bool

class IsMessageLongEnoughStep(BaseCustomStep):
    InputModel = IsMessageLongEnoughInput
    OutputModel = IsMessageLongEnoughOutput

    async def execute(self, input_data: IsMessageLongEnoughInput) -> IsMessageLongEnoughOutput:
        """Validates if a message's length is greater than 5."""
        print(f"[CUSTOM CODE] Validating message: '{input_data.message}'")
        result = len(input_data.message or "") > 5
        return IsMessageLongEnoughOutput(is_long_enough=result)