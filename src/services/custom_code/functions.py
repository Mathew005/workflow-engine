# This file is for YOUR custom Python logic.
# When you need to do something the declarative YAML can't handle
# (e.g., complex calculations, custom data transformations, specific DB calls),
# you write a simple Python function here and register it in __init__.py.

from typing import Dict, Any

# --- Example Functions ---

def is_message_long_enough(message: str) -> bool:
    """A simple synchronous function for data validation."""
    print(f"[CUSTOM CODE] Validating message: '{message}'")
    return len(message or "") > 5

def get_user_profile_by_intent(analysis_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    A synchronous function that simulates fetching user data based on LLM analysis.
    In a real application, this function could query a database.
    """
    intent = analysis_result.get('user_intent', 'UNKNOWN')
    print(f"[CUSTOM CODE] Fetching user profile for intent: {intent}")
    
    if intent == "ELABORATE":
        return {"user_id": "user-123", "tier": "premium", "preferences": ["details", "tech_specs"]}
    else:
        return {"user_id": "user-123", "tier": "standard", "preferences": ["summary"]}

# You could also define async functions for I/O-bound tasks
async def fetch_external_data(some_id: str) -> dict:
    """An example of an async function for non-blocking I/O."""
    # import httpx
    # async with httpx.AsyncClient() as client:
    #     response = await client.get(f"https://api.example.com/data/{some_id}")
    #     return response.json()
    print(f"[CUSTOM CODE] Pretending to fetch external data for ID: {some_id}")
    return {"external_id": some_id, "data": "some important data from a slow API"}