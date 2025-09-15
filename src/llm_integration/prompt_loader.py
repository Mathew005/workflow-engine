from typing import Dict, Any
import re
from pathlib import Path

def load_prompt_template(filename: str, replacements: Dict[str, Any], base_path: Path) -> str:
    """
    Loads a prompt template from the 'prompts' subdirectory within a given workflow package path.
    """
    prompt_file_path = base_path / "prompts" / filename
    try:
        with open(prompt_file_path, "r") as f:
            template = f.read()
    except FileNotFoundError:
        raise ValueError(f"Prompt template file not found at path: {prompt_file_path}")

    for key, value in replacements.items():
        template = template.replace(f"<{key}>", str(value))

    missed = re.findall(r'<([^>]+)>', template)
    if missed:
        raise ValueError(f"Missing replacements for placeholders in {filename}: {missed}")

    return template