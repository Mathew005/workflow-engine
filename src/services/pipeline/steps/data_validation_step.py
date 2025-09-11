from .base_step import PipelineStep
from src.domain.models import TurnContext
from src.services.pipeline.resource_provider import ResourceProvider

class DataValidationStep(PipelineStep):
    """
    A simple, SYNCHRONOUS step that performs a basic validation check.
    It runs in parallel with other steps that have no dependencies.
    """
    @property
    def name(self) -> str:
        return "data_validation"

    def get_required_inputs(self) -> list[str]:
        return ["user_message"]

    def get_outputs(self) -> list[str]:
        return ["is_message_valid"]

    async def execute(self, context: TurnContext, resources: ResourceProvider) -> TurnContext:
        context.log(f"Executing step: {self.name}")
        message = context.get("user_message", "")
        
        # Simple synchronous logic
        is_valid = len(message) > 5
        
        context.set("is_message_valid", is_valid)
        context.log(f"Validation result: {is_valid}")
        return context