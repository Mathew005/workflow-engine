from typing import Dict
import re

def load_prompt_template(filename: str, replacements: Dict[str, str]) -> str:
    """Loads a prompt template and replaces placeholders."""
    try:
        # Assuming templates are in a fixed location relative to this file
        with open(f"src/llm_integration/templates/{filename}", "r") as f:
            template = f.read()
    except FileNotFoundError:
        raise ValueError(f"Prompt template file not found: {filename}")

    for key, value in replacements.items():
        template = template.replace(f"<{key}>", str(value))

    missed = re.findall(r'<([^>]+)>', template)
    if missed:
        raise ValueError(f"Missing replacements for placeholders in {filename}: {missed}")

    return template