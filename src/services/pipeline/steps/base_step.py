from abc import ABC, abstractmethod
from typing import List
from src.domain.models import TurnContext
from src.services.pipeline.resource_provider import ResourceProvider

class PipelineStep(ABC):
    """
    An abstract base class for any component in the analysis pipeline.
    
    Each step is a self-contained unit of logic that declares its dependencies (inputs)
    and the data it produces (outputs).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """A unique, machine-readable name for this step (e.g., 'parallel_analysis')."""
        pass

    @abstractmethod
    def get_required_inputs(self) -> List[str]:
        """A list of keys that this step requires to be present in the TurnContext before it can run."""
        pass

    @abstractmethod
    def get_outputs(self) -> List[str]:
        """A list of keys that this step guarantees it will add to the TurnContext upon successful completion."""
        pass

    @abstractmethod
    async def execute(self, context: TurnContext, resources: ResourceProvider) -> TurnContext:
        """
        Executes the step's logic. It reads its required inputs from the context,
        performs its action (e.g., calling an LLM, querying a DB), and writes its
        outputs back into the context before returning it.
        """
        pass