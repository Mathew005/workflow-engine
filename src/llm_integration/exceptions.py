# src/llm_integration/exceptions.py

class APIError(Exception):
    """Base exception for all API-related errors."""
    pass

class RateLimitError(APIError):
    """Raised when the API rate limit is exceeded."""
    pass

class QuotaError(APIError):
    """Raised when the API quota is exceeded or the key is invalid."""
    pass

class BadResponseError(APIError):
    """Raised when the API returns a malformed or invalid response (e.g., bad JSON)."""
    pass

class APIUnavailableError(APIError):
    """Raised when the API is temporarily unavailable (e.g., 500/503 errors)."""
    pass