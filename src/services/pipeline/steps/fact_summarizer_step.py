import json
from .base_step import PipelineStep
from src.domain.models import TurnContext
from src.services.pipeline.resource_provider import ResourceProvider
from src.llm_integration.prompt_loader import load_prompt_template

class FactSummarizerStep(PipelineStep):
    """
    An ASYNC step that depends on the output of another step (`memory_fetcher`).
    It demonstrates a sequential dependency.
    """
    @property
    def name(self) -> str:
        return "fact_summarizer"

    def get_required_inputs(self) -> list[str]:
        return ["fetched_memories"]

    def get_outputs(self) -> list[str]:
        return ["fact_summary"]

    async def execute(self, context: TurnContext, resources: ResourceProvider) -> TurnContext:
        context.log(f"Executing step: {self.name}")
        memories = context.get("fetched_memories", [])
        
        if not memories:
            context.set("fact_summary", "No facts to summarize.")
            return context

        gemini_client = resources.get_gemini_client()
        prompt = load_prompt_template("2_fact_summarizer.txt", {
            "facts_json": json.dumps(memories)
        })
        context.set_step_prompt(self.name, prompt)

        result = await gemini_client.call_gemini_async(prompt, self.name)
        summary = result['response_json'].get('summary', 'Failed to generate summary.')
        
        context.set("fact_summary", summary)
        context.log(f"Fact summary generated.")
        return context