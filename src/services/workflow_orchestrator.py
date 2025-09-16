from __future__ import annotations
from typing import TYPE_CHECKING, AsyncGenerator, Dict, Any
from pathlib import Path
import asyncio
import time

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
    Runs the full workflow, yielding events for logs, lifecycle changes,
    and sub-workflow events.
    """
    gemini_client = GeminiClient()
    resources.set_gemini_client(gemini_client)
    
    event_queue = asyncio.Queue()
    resources.set_event_queue(event_queue)

    graph = LangGraphBuilder(workflow_def, resources, workflow_path).build()
    
    merged_stream_queue = asyncio.Queue()

    async def stream_graph_events():
        async for event in graph.astream_events(initial_state, version="v1"):
            await merged_stream_queue.put({"source": "graph", "payload": event})
        await merged_stream_queue.put(None)

    async def stream_sub_workflow_events():
        while True:
            event = await event_queue.get()
            if event is None: break
            await merged_stream_queue.put({"source": "sub_workflow", "payload": event})
            event_queue.task_done()

    graph_task = asyncio.create_task(stream_graph_events())
    sub_workflow_task = asyncio.create_task(stream_sub_workflow_events())

    stop_count = 0
    while stop_count < 1:
        event_wrapper = await merged_stream_queue.get()
        if event_wrapper is None:
            stop_count += 1; continue

        source, payload = event_wrapper["source"], event_wrapper["payload"]

        if source == "graph":
            event_name = payload["event"]
            if event_name == "on_chain_start" and payload["name"] != "__root__":
                yield {"type": "lifecycle_update", "data": {"step_name": payload["name"], "status": "RUNNING"}}
            
            elif event_name == "on_chain_end":
                node_output = payload["data"].get("output")
                if isinstance(node_output, dict) and "debug_log" in node_output and node_output["debug_log"]:
                    log_data = node_output["debug_log"][0]
                    log_data['timestamp'] = time.time()
                    yield {"type": "log", "data": log_data}
                    yield {"type": "lifecycle_update", "data": {"step_name": log_data["step_name"], "status": log_data["status"].upper()}}
            
            elif event_name == "on_graph_end":
                final_state = payload["data"].get("output")
                yield {"type": "result", "data": final_state}
        
        elif source == "sub_workflow":
            yield payload

    await event_queue.put(None)
    await asyncio.gather(graph_task, sub_workflow_task)