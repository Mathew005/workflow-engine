from abc import ABC, abstractmethod
from typing import Dict, Any

from src.domain.models import TurnContext
from src.services.pipeline.resource_provider import ResourceProvider

class BaseExecutor(ABC):
    """
    Abstract base class for all generic step executors.
    An executor is a reusable piece of logic that performs a specific type of action (e.g., call an LLM, run code).
    It is configured entirely from the params in a workflow YAML file.
    """
    def __init__(self, step_name: str, params: Dict[str, Any]):
        self.step_name = step_name
        self.params = params

    @abstractmethod
    async def execute(self, context: TurnContext, resources: ResourceProvider) -> None:
        """
        Executes the step's logic. This method is designed to be self-contained.
        It reads from the context, performs its action, and writes its results back to the context.
        It does not return the context; it mutates it directly.
        """
        pass