from __future__ import annotations
import asyncio
from typing import TYPE_CHECKING, Optional, Dict, Any

from src.data_layer.database_manager import DatabaseManager

if TYPE_CHECKING:
    from src.llm_integration.gemini_client import GeminiClient

class ResourceProvider:
    """
    A container for stateful resources. It now includes an event queue for
    streaming real-time updates from nested workflow executions.
    """
    def __init__(self, db_manager: DatabaseManager):
        self._db_manager = db_manager
        self._gemini_client: GeminiClient | None = None
        self._event_queue: Optional[asyncio.Queue] = None

    def set_gemini_client(self, client: GeminiClient) -> None:
        """Sets the Gemini client for the current run."""
        self._gemini_client = client

    def set_event_queue(self, queue: asyncio.Queue) -> None:
        """Sets the event queue for the current run."""
        self._event_queue = queue

    async def emit_event(self, event: Dict[str, Any]) -> None:
        """Emits an event to the orchestrator's queue if it exists."""
        if self._event_queue:
            await self._event_queue.put(event)

    def get_db_manager(self) -> DatabaseManager:
        """Returns the cached database manager."""
        return self._db_manager

    def get_gemini_client(self) -> GeminiClient:
        """Returns the runtime Gemini client."""
        if not self._gemini_client:
            raise ValueError("GeminiClient not initialized for this run.")
        return self._gemini_client