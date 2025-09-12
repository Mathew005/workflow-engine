import asyncio
from typing import Dict, Any, AsyncGenerator

async def stream_graph_events(graph: Any, initial_state: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Executes a LangGraph using the stable `astream_events` method and yields 
    structured debug records in real-time.
    """
    # astream_events is a higher-level, more stable API than astream_log.
    # It yields dictionaries with a clear event name and associated data.
    async for event in graph.astream_events(initial_state, version="v1"):
        
        # We listen for the 'on_chain_end' event, which fires when a node finishes.
        if event["event"] == "on_chain_end":
            # The node's output is in the event data.
            node_output = event["data"].get("output")

            # Our nodes now return a 'debug_log' list containing the record.
            if isinstance(node_output, dict) and "debug_log" in node_output and node_output["debug_log"]:
                # We yield the record from the list, which the UI will then display.
                yield node_output["debug_log"][0]
                # Give the UI a tiny moment to render the update.
                await asyncio.sleep(0.01)