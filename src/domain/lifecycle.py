from enum import Enum

class StepLifecycle(str, Enum):
    """Defines the possible states for a step in the workflow lifecycle."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"