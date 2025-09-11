from src.data_layer.database_manager import DatabaseManager
from src.llm_integration.gemini_client import GeminiClient

class ResourceProvider:
    """
    A simple container to hold and provide access to external resources like
    database connections and API clients. This makes it easy to pass all
    necessary tools to each pipeline step.
    """
    def __init__(self, db_manager: DatabaseManager, gemini_client: GeminiClient):
        self._db_manager = db_manager
        self._gemini_client = gemini_client
        # In the future, you could add:
        # self._vector_db_client = VectorDBClient()
        # self._cache_client = CacheClient()

    def get_db_manager(self) -> DatabaseManager:
        return self._db_manager

    def get_gemini_client(self) -> GeminiClient:
        return self._gemini_client