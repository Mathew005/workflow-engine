from typing import Dict, Any
import re

def load_prompt_template(filename: str, replacements: Dict[str, Any]) -> str:
    """Loads a prompt template and replaces placeholders."""
    try:
        with open(f"src/llm_integration/templates/{filename}", "r") as f:
            template = f.read()
    except FileNotFoundError:
        raise ValueError(f"Prompt template file not found: {filename}")

    for key, value in replacements.items():
        # Ensure value is a string before replacement
        template = template.replace(f"<{key}>", str(value))

    missed = re.findall(r'<([^>]+)>', template)
    if missed:
        raise ValueError(f"Missing replacements for placeholders in {filename}: {missed}")

    return template