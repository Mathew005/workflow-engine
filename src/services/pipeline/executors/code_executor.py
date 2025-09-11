from .base_executor import BaseExecutor
from typing import Dict, Any, Callable
import inspect

from src.domain.models import TurnContext
from src.services.pipeline.resource_provider import ResourceProvider
from src.services.custom_code import CODE_STEP_REGISTRY

class CodeExecutor(BaseExecutor):
    """
    A generic executor for running registered Python functions.
    It allows extending the engine with custom logic without creating new executor classes.

    Expected params:
    - function_name (str): The name of the function as registered in CODE_STEP_REGISTRY.
    - input_key (str): The context key whose value will be passed to the function.
    - output_key (str): The context key where the function's return value will be stored.
    """
    def __init__(self, step_name: str, params: Dict[str, Any]):
        super().__init__(step_name, params)
        self.function_name: str = self.params.get('function_name')
        self.input_key: str = self.params.get('input_key')
        self.output_key: str = self.params.get('output_key')

        if not all([self.function_name, self.output_key]):
            raise ValueError(f"[CodeExecutor: {self.step_name}] Missing required params: 'function_name' and 'output_key'.")

        self.func: Callable = CODE_STEP_REGISTRY.get(self.function_name)
        if not self.func:
            raise ValueError(f"[CodeExecutor: {self.step_name}] Function '{self.function_name}' not found in the code registry.")

    async def execute(self, context: TurnContext, resources: ResourceProvider) -> None:
        context.log(f"Executing step '{self.step_name}' with CodeExecutor (function: {self.function_name}).")
        
        # 1. Get input from context
        input_data = context.get(self.input_key)
        context.set_step_io(self.step_name, {self.input_key: input_data}, [self.output_key])

        # 2. Execute the registered function
        try:
            # Check if the function is async or sync
            if inspect.iscoroutinefunction(self.func):
                result = await self.func(input_data)
            else:
                result = self.func(input_data)
        except Exception as e:
            context.log(f"ERROR in step '{self.step_name}': Function '{self.function_name}' failed with error: {e}")
            raise

        # 3. Set the output in the context
        context.set(self.output_key, result)
        
        context.log(f"Step '{self.step_name}' completed. Wrote result to '{self.output_key}'.")