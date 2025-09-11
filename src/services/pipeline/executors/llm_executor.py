import json
from .base_executor import BaseExecutor
from typing import Dict, Any

from src.domain.models import TurnContext
from src.services.pipeline.resource_provider import ResourceProvider
from src.llm_integration.prompt_loader import load_prompt_template

class LlmExecutor(BaseExecutor):
    """
    A generic executor for making asynchronous calls to a language model.
    It is configured via the 'params' block in a workflow step.
    
    Expected params:
    - prompt_template (str): The filename of the prompt template.
    - input_mapping (dict): Maps context keys to placeholders in the prompt.
    - output_key (str): The context key where the LLM's JSON response will be stored.
    """
    def __init__(self, step_name: str, params: Dict[str, Any]):
        super().__init__(step_name, params)
        self.prompt_template: str = self.params.get('prompt_template')
        self.input_mapping: dict = self.params.get('input_mapping', {})
        self.output_key: str = self.params.get('output_key')

        if not all([self.prompt_template, self.output_key]):
            raise ValueError(f"[LlmExecutor: {step_name}] Missing required params: 'prompt_template' and 'output_key'.")

    async def execute(self, context: TurnContext, resources: ResourceProvider) -> None:
        context.log(f"Executing step '{self.step_name}' with LlmExecutor.")
        
        # 1. Resolve inputs from context
        resolved_inputs = context.resolve_inputs(self.input_mapping)
        context.set_step_io(self.step_name, resolved_inputs, [self.output_key])

        # 2. Load and format prompt
        try:
            prompt = load_prompt_template(self.prompt_template, resolved_inputs)
            context.set_step_prompt(self.step_name, prompt)
        except ValueError as e:
            context.log(f"ERROR in step '{self.step_name}': {e}")
            raise

        # 3. Call Gemini client
        gemini_client = resources.get_gemini_client()
        result = await gemini_client.call_gemini_async(prompt, self.step_name)
        response_json = result.get('response_json', {})

        # 4. Set outputs in context
        # The main output is the full JSON object
        context.set(self.output_key, response_json)

        # For granular dependency tracking, also set sub-keys
        # e.g., if output_key is 'analysis' and json has 'intent',
        # a key 'analysis_intent' is created.
        if isinstance(response_json, dict):
            for sub_key, sub_value in response_json.items():
                granular_key = f"{self.output_key.replace('.', '_')}_{sub_key}"
                context.set(granular_key, sub_value)
                # This makes dependencies like "initial_analysis.user_intent" possible
        
        context.log(f"Step '{self.step_name}' completed. Wrote result to '{self.output_key}'.")