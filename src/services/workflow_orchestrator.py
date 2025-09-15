from __future__ import annotations
from typing import TYPE_CHECKING, AsyncGenerator, Dict, Any
from pathlib import Path

from src.llm_integration.gemini_client import GeminiClient
from src.services.langgraph_builder import LangGraphBuilder

if TYPE_CHECKING:
    from src.services.pipeline.resource_provider import ResourceProvider

async def run_workflow_streaming(
    resources: ResourceProvider, 
    workflow_def: dict, 
    workflow_path: Path,
    initial_state: dict
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Runs the full workflow, yielding events for logs, lifecycle changes, and the final result.
    """
    gemini_client = GeminiClient()
    resources.set_gemini_client(gemini_client)
    
    graph = LangGraphBuilder(workflow_def, resources, workflow_path).build()

    async for event in graph.astream_events(initial_state, version="v1"):
        event_type = event["event"]

        # Event when a node (step) starts its execution
        if event_type == "on_chain_start":
            # The root event is the whole graph, we only care about individual nodes.
            if event["name"] != "__root__":
                yield {
                    "type": "lifecycle_update",
                    "data": {"step_name": event["name"], "status": "RUNNING"}
                }
        
        # Event when a node (step) has finished its execution
        elif event_type == "on_chain_end":
            node_output = event["data"].get("output")
            if isinstance(node_output, dict) and "debug_log" in node_output and node_output["debug_log"]:
                log_data = node_output["debug_log"][0]
                yield {"type": "log", "data": log_data}
                
                # Use the status from the debug log ("Completed" or "Failed") for the lifecycle update
                yield {
                    "type": "lifecycle_update",
                    "data": {"step_name": log_data["step_name"], "status": log_data["status"].upper()}
                }
        
        # Event when the entire graph has finished
        elif event_type == "on_graph_end":
            final_state = event["data"].get("output")
            yield {"type": "result", "data": final_state}