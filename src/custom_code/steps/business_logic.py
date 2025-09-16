from pydantic import BaseModel, Field
from typing import Dict, Any

from src.custom_code.base import BaseCustomStep

class DetermineFinalActionInput(BaseModel):
    report: Dict[str, Any]

class DetermineFinalActionOutput(BaseModel):
    action: str = Field(..., description="The final business action to take.")
    reason: str

class DetermineFinalActionStep(BaseCustomStep):
    """
    Applies business logic to a text analysis report to decide on a concrete action.
    """
    InputModel = DetermineFinalActionInput
    OutputModel = DetermineFinalActionOutput

    async def execute(self, input_data: DetermineFinalActionInput) -> DetermineFinalActionOutput:
        summary = input_data.report.get("summary", "")
        stats = input_data.report.get("statistics", {})
        word_count = stats.get("word_count", 0)

        if "error" in summary.lower() or "bug" in summary.lower():
            return DetermineFinalActionOutput(
                action="ROUTE_TO_SUPPORT",
                reason=f"Keyword 'error' or 'bug' detected in summary."
            )
        
        if word_count < 50:
            return DetermineFinalActionOutput(
                action="FLAG_FOR_REVIEW",
                reason=f"Review is very short ({word_count} words), may lack detail."
            )

        return DetermineFinalActionOutput(
            action="ARCHIVE_AS_POSITIVE_FEEDBACK",
            reason="Review appears to be standard positive feedback."
        )