from __future__ import annotations
from typing import TYPE_CHECKING, AsyncGenerator, Dict, Any

from src.llm_integration.gemini_client import GeminiClient
from src.services.langgraph_builder import LangGraphBuilder

if TYPE_CHECKING:
    from src.services.pipeline.resource_provider import ResourceProvider

async def run_workflow_streaming(
    resources: ResourceProvider, 
    workflow_def: dict, 
    initial_state: dict
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Runs the full workflow, yielding events for logs and the final result.
    This function is UI-agnostic.

    Event Types:
    - {"type": "log", "data": <debug_record>}
    - {"type": "result", "data": <final_state>}
    """
    # 1. Instantiate client and build graph inside the async context.
    gemini_client = GeminiClient()
    resources.set_gemini_client(gemini_client)
    graph = LangGraphBuilder(workflow_def, resources).build()

    # 2. Use astream_events to get both logs and the final state in a single run.
    async for event in graph.astream_events(initial_state, version="v1"):
        # 3. Yield log records as they are produced.
        if event["event"] == "on_chain_end":
            node_output = event["data"].get("output")
            if isinstance(node_output, dict) and "debug_log" in node_output and node_output["debug_log"]:
                yield {"type": "log", "data": node_output["debug_log"][0]}
        
        # 4. Yield the final state at the very end.
        if event["event"] == "on_graph_end":
            final_state = event["data"].get("output")
            yield {"type": "result", "data": final_state}
