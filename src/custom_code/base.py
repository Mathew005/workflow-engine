from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import Type

from src.services.pipeline.resource_provider import ResourceProvider

class BaseCustomStep(ABC):
    """
    Abstract base class for all custom code steps.
    It enforces a contract for input/output validation and execution.
    """
    # Pydantic models provide automatic validation and serve as documentation.
    # These MUST be defined in the subclass.
    InputModel: Type[BaseModel]
    OutputModel: Type[BaseModel]

    def __init__(self, resources: ResourceProvider):
        self.resources = resources

    @abstractmethod
    async def execute(self, input_data: BaseModel) -> BaseModel:
        """The core logic of the step lives here."""
        pass