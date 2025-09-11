import google.generativeai as genai
import time
import json
import asyncio
from typing import Dict, Any, Callable, Awaitable
from src.llm_integration.key_manager import key_manager
from src.llm_integration.exceptions import (
    APIError, RateLimitError, QuotaError, BadResponseError, APIUnavailableError
)

FATAL_KEY_ERROR_SUBSTRINGS = (
    'api key not valid',
    'permission denied',
    'invalid authentication',
    'api key expired'
)

class GeminiClient:
    def __init__(self):
        self.key_manager = key_manager
        active_key = self.key_manager.get_active_key()
        if not active_key:
            raise ValueError("CRITICAL: No active Gemini API Key found in .env file.")
        
        genai.configure(api_key=active_key)
        self.model = genai.GenerativeModel('gemini-1.5-flash')

    async def _execute_gemini_call_async(self, prompt_content: Any, step_name: str) -> Dict[str, Any]:
        start_time = time.time()
        response = await self.model.generate_content_async(prompt_content)
        end_time = time.time()
        
        cleaned_text = response.text.strip().replace("```json", "").replace("```", "").strip()
        
        try:
            parsed_json = json.loads(cleaned_text)
            return {
                "response_json": parsed_json,
                "time_taken_ms": int((end_time - start_time) * 1000),
            }
        except json.JSONDecodeError as e:
            raise BadResponseError(f"Step '{step_name}' failed to decode LLM JSON. Raw text: '{cleaned_text}'. Error: {e}")

    async def _call_with_resilience_async(self, api_call_func: Callable[[], Awaitable[Dict[str, Any]]]) -> Dict[str, Any]:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                return await api_call_func()
            except Exception as e:
                error_str = str(e).lower()
                
                is_quota_error = "quota" in error_str
                is_fatal_key_error = any(sub in error_str for sub in FATAL_KEY_ERROR_SUBSTRINGS)

                if is_quota_error or is_fatal_key_error:
                    error_type = "Quota exceeded" if is_quota_error else "Invalid key"
                    print(f"[WARNING] {error_type} for the current API key (async).")
                    new_key = self.key_manager.rotate_to_next_key()
                    if new_key:
                        print("[INFO] Rotating to the next available API key and retrying (async)...")
                        genai.configure(api_key=new_key)
                        # We need to retry the original function, not this resilience wrapper
                        return await self._call_with_resilience_async(api_call_func) 
                    else:
                        raise QuotaError("All API keys have been exhausted or are invalid.")
                
                if "rate limit" in error_str: raise RateLimitError(f"Rate limit exceeded: {e}")
                if isinstance(e, BadResponseError): raise 
                if "500" in error_str or "503" in error_str or "unavailable" in error_str:
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt
                        print(f"[WARNING] Async API unavailable, retrying in {wait_time}s...")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        raise APIUnavailableError(f"Async API is unavailable after {max_retries} retries: {e}")
                raise APIError(f"An unexpected async API error occurred: {e}")
        raise APIError("All async retry attempts failed.")

    async def call_gemini_async(self, prompt: str, step_name: str) -> Dict[str, Any]:
        async def api_call():
            return await self._execute_gemini_call_async(prompt, step_name)
        return await self._call_with_resilience_async(api_call)
