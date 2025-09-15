import importlib
import inspect
from pathlib import Path
from typing import Dict, Type

from .base import BaseCustomStep

CODE_STEP_REGISTRY: Dict[str, Type[BaseCustomStep]] = {}

def _register_steps():
    """
    Dynamically discovers and registers all BaseCustomStep subclasses
    in the 'steps' subdirectory, using their file path for namespacing.
    """
    steps_base_dir = Path(__file__).parent / "steps"
    
    for f in steps_base_dir.rglob("*.py"):
        if f.name.startswith("_"):
            continue

        relative_path = f.relative_to(steps_base_dir)
        namespace = ".".join(relative_path.with_suffix("").parts)
        module_name = f"src.services.custom_code.steps.{namespace}"

        try:
            module = importlib.import_module(module_name)
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, BaseCustomStep) and obj is not BaseCustomStep:
                    qualified_name = f"{namespace}.{name}"
                    
                    if qualified_name in CODE_STEP_REGISTRY:
                        raise NameError(
                            f"Duplicate custom step name '{qualified_name}' found. "
                            f"Please ensure all class names within a file are unique."
                        )
                    
                    CODE_STEP_REGISTRY[qualified_name] = obj
                    print(f"[INFO] Auto-registered custom step: '{qualified_name}'")

        except Exception as e:
            print(f"[ERROR] Failed to load or register steps from {f.name}: {e}")

_register_steps()