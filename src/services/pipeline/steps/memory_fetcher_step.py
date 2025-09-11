from .base_step import PipelineStep
from src.domain.models import TurnContext
from src.services.pipeline.resource_provider import ResourceProvider

class MemoryFetcherStep(PipelineStep):
    """
    An ASYNC step that fetches data from an external resource (the database).
    This simulates an I/O-bound operation.
    """
    @property
    def name(self) -> str:
        return "memory_fetcher"

    def get_required_inputs(self) -> list[str]:
        return ["session_id", "active_sub_topic_id"]

    def get_outputs(self) -> list[str]:
        return ["fetched_memories"]

    async def execute(self, context: TurnContext, resources: ResourceProvider) -> TurnContext:
        context.log(f"Executing step: {self.name}")
        session_id = context.get("session_id")
        active_topic_id = context.get("active_sub_topic_id")
        
        db = resources.get_db_manager()
        
        memories = await db.get_memory_nodes_for_topic(session_id, active_topic_id)
        
        context.set("fetched_memories", memories)
        context.log(f"Fetched {len(memories)} memories from the database.")
        return context