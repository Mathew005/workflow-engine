from typing import Dict, Any
import re
from pathlib import Path

def load_prompt_template(filename: str, replacements: Dict[str, Any], base_path: Path) -> str:
    """
    Loads a prompt template, first checking the workflow's local 'prompts'
    directory, and falling back to a central 'shared_prompts' directory.
    """
    local_prompt_path = base_path / "prompts" / filename
    
    # The shared directory is located alongside the main 'workflows' directory.
    shared_prompt_path = base_path.parent.parent / "shared_prompts" / filename

    prompt_file_path = None
    if local_prompt_path.exists():
        prompt_file_path = local_prompt_path
    elif shared_prompt_path.exists():
        prompt_file_path = shared_prompt_path
    else:
        raise FileNotFoundError(
            f"Prompt template '{filename}' not found. Searched in:\n"
            f"- Local: {local_prompt_path}\n"
            f"- Shared: {shared_prompt_path}"
        )

    try:
        with open(prompt_file_path, "r") as f:
            template = f.read()
    except Exception as e:
        raise IOError(f"Failed to read prompt file at {prompt_file_path}: {e}")

    for key, value in replacements.items():
        template = template.replace(f"<{key}>", str(value))

    missed = re.findall(r'<([^>]+)>', template)
    if missed:
        raise ValueError(f"Missing replacements for placeholders in {filename}: {missed}")

    return template