class DatabaseManager:
    """A placeholder for database interactions. History feature is disabled."""
    def __init__(self, mongo_uri: str):
        print(f"[INFO] DatabaseManager initialized (history feature disabled).")
        self.mongo_uri = mongo_uri

    def is_connected(self) -> bool:
        """History feature is disabled, so this will always be false."""
        return False