from __future__ import annotations
from typing import TYPE_CHECKING

from src.data_layer.database_manager import DatabaseManager

if TYPE_CHECKING:
    from src.llm_integration.gemini_client import GeminiClient

class ResourceProvider:
    """
    A container for stateful resources. The GeminiClient is set at runtime
    to ensure it's created within the correct asyncio event loop.
    """
    def __init__(self, db_manager: DatabaseManager):
        self._db_manager = db_manager
        self._gemini_client: GeminiClient | None = None

    def set_gemini_client(self, client: GeminiClient) -> None:
        """Sets the Gemini client for the current run."""
        self._gemini_client = client

    def get_db_manager(self) -> DatabaseManager:
        """Returns the cached database manager."""
        return self._db_manager

    def get_gemini_client(self) -> GeminiClient:
        """Returns the runtime Gemini client."""
        if not self._gemini_client:
            raise ValueError("GeminiClient not initialized for this run.")
        return self._gemini_client
