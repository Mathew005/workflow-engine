import re
import threading
from typing import List, Optional

class ApiKeyManager:
    """
    A thread-safe singleton to manage and rotate Gemini API keys from a .env file.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(ApiKeyManager, cls).__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self, env_path: str = ".env"):
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            
            self.env_path = env_path
            self.keys: List[dict] = []
            self.current_key_index: Optional[int] = None
            self._load_keys()
            self._initialized = True
            print(f"[INFO] ApiKeyManager initialized with {len(self.keys)} keys.")

    def _load_keys(self):
        """Parses the .env file to find all active and commented-out Gemini keys."""
        try:
            with open(self.env_path, "r") as f:
                content = f.read()
        except FileNotFoundError:
            raise ValueError(f"CRITICAL: .env file not found at path: {self.env_path}")

        pattern = re.compile(r'^(#)?\s*GEMINI_API_KEY\s*=\s*"(.*?)"', re.MULTILINE)
        matches = pattern.finditer(content)

        for i, match in enumerate(matches):
            is_commented = match.group(1) == '#'
            key_value = match.group(2)
            if key_value:
                self.keys.append({"key": key_value, "is_active": not is_commented})
                if not is_commented:
                    # Only set the first uncommented key as active
                    if self.current_key_index is None:
                        self.current_key_index = len(self.keys) - 1
        
        # If no uncommented key was found, activate the first one
        if self.current_key_index is None and self.keys:
            self.current_key_index = 0
            self.keys[0]["is_active"] = True
            self._save_keys()

    def _save_keys(self):
        """Rewrites the .env file with the current state of active/commented keys."""
        try:
            with open(self.env_path, "r") as f:
                lines = f.readlines()
        except FileNotFoundError:
            return

        key_pattern = re.compile(r'GEMINI_API_KEY\s*=\s*".*?"')
        key_iter = iter(self.keys)
        
        new_lines = []
        for line in lines:
            if key_pattern.search(line):
                try:
                    key_state = next(key_iter)
                    prefix = "" if key_state["is_active"] else "#"
                    new_lines.append(f'{prefix}GEMINI_API_KEY="{key_state["key"]}"\n')
                except StopIteration:
                    # This handles cases where there are more key lines in the file
                    # than we parsed, which shouldn't happen with the current logic.
                    new_lines.append(line) 
            else:
                new_lines.append(line)

        with open(self.env_path, "w") as f:
            f.writelines(new_lines)
        print(f"[INFO] .env file updated. Active key is now at index {self.current_key_index}.")

    def get_active_key(self) -> Optional[str]:
        """Returns the currently active API key."""
        if self.current_key_index is not None and self.keys:
            return self.keys[self.current_key_index]["key"]
        return None

    def rotate_to_next_key(self) -> Optional[str]:
        """
        Deactivates the current key, activates the next one, and saves the state.
        Returns the new key, or None if all keys have been exhausted.
        """
        with self._lock:
            if self.current_key_index is None:
                return None

            self.keys[self.current_key_index]["is_active"] = False
            
            next_index = self.current_key_index + 1
            if next_index >= len(self.keys):
                print("[ERROR] All API keys have been exhausted.")
                self.current_key_index = None
                self._save_keys() # Save the state where all keys are commented out
                return None
            
            self.current_key_index = next_index
            self.keys[self.current_key_index]["is_active"] = True
            
            self._save_keys()
            return self.keys[self.current_key_index]["key"]

key_manager = ApiKeyManager()