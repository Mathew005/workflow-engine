import json
from .base_step import PipelineStep
from src.domain.models import TurnContext, AnalysisResult
from src.services.pipeline.resource_provider import ResourceProvider
from src.llm_integration.prompt_loader import load_prompt_template

class ParallelAnalysisStep(PipelineStep):
    """
    An ASYNC step that performs a broad analysis of the user's message.
    It runs in parallel with other steps that have no dependencies.
    """
    
    @property
    def name(self) -> str:
        return "parallel_analysis"

    def get_required_inputs(self) -> list[str]:
        return ["user_message"]

    def get_outputs(self) -> list[str]:
        return ["analysis_result"]

    async def execute(self, context: TurnContext, resources: ResourceProvider) -> TurnContext:
        context.log(f"Executing step: {self.name}")
        user_message = context.get("user_message")
        
        gemini_client = resources.get_gemini_client()

        prompt = load_prompt_template("1_initial_analysis.txt", {
            "user_message": user_message
        })
        context.set_step_prompt(self.name, prompt)
        
        result = await gemini_client.call_gemini_async(prompt, self.name)
        
        analysis_obj = AnalysisResult.model_validate(result['response_json'])
        context.set("analysis_result", analysis_obj)
        context.log(f"Step '{self.name}' completed. Intent found: {analysis_obj.user_intent}")
        
        return context