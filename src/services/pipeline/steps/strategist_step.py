import json
from .base_step import PipelineStep
from src.domain.models import TurnContext
from src.services.pipeline.resource_provider import ResourceProvider
from src.llm_integration.prompt_loader import load_prompt_template

class StrategistStep(PipelineStep):
    """
    An ASYNC step with complex dependencies. It waits for multiple parallel
    branches to complete before running.
    """
    @property
    def name(self) -> str:
        return "strategist"

    def get_required_inputs(self) -> list[str]:
        return ["analysis_result", "fact_summary", "is_message_valid"]

    def get_outputs(self) -> list[str]:
        return ["chosen_strategy", "strategy_reasoning"]

    async def execute(self, context: TurnContext, resources: ResourceProvider) -> TurnContext:
        context.log(f"Executing step: {self.name}")
        
        # Gather inputs from the context
        analysis = context.get("analysis_result")
        summary = context.get("fact_summary")
        is_valid = context.get("is_message_valid")

        prompt_context = {
            "user_intent": analysis.user_intent if analysis else "UNKNOWN",
            "fact_summary": summary,
            "is_valid": is_valid
        }

        gemini_client = resources.get_gemini_client()
        prompt = load_prompt_template("3_strategist.txt", {
            "prompt_context_json": json.dumps(prompt_context)
        })
        context.set_step_prompt(self.name, prompt)

        result = await gemini_client.call_gemini_async(prompt, self.name)
        strategy_output = result['response_json']
        
        context.set("chosen_strategy", strategy_output.get("chosen_strategy"))
        context.set("strategy_reasoning", strategy_output.get("reasoning"))
        context.log(f"Strategy chosen: {strategy_output.get('chosen_strategy')}")
        return context