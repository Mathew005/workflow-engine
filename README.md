# Conversational AI Workflow Engine

This project provides a dynamic, extensible, and configuration-driven engine for building and testing complex, multi-step conversational AI pipelines.

## Purpose and Goal

The primary goal of this architecture is **maximum flexibility and extensibility**. Traditional conversational AI logic is often hardcoded, making it difficult to modify, experiment with, or debug. This engine solves that problem by treating the AI's "thought process" not as a monolithic script, but as a **workflow of independent, hotswappable components** called "Pipeline Steps".

The entire flow of logic is defined in a simple `workflow.yaml` file. This allows developers and researchers to rapidly reconfigure the AI's reasoning—adding new capabilities (like a vector database search), changing the order of operations, or running processes in parallel—simply by editing a configuration file, without touching the core orchestration code.

### Core Architectural Concepts

1.  **The Pipeline Step (Component):** Each unit of logic (an LLM call, a database query, a data transformation) is an isolated, self-contained `PipelineStep` class. Each step formally declares the data it needs (inputs) and the data it will produce (outputs).

2.  **The Workflow Definition (Blueprint):** A `workflow.yaml` file defines the sequence and dependencies of all pipeline steps. This creates a Directed Acyclic Graph (DAG) that the engine executes, allowing for both sequential and parallel processing branches.

3.  **The Central Turn Context (Data Bus):** A single, dictionary-like `TurnContext` object is passed through the entire workflow. Each step reads its required data from this context and writes its results back, making the data flow explicit and easy to trace.

4.  **The Resource Provider (Toolbox):** A central provider holds connections to all external services (e.g., Gemini Client, Database Manager, Vector DB Client). Steps request the tools they need from this provider, keeping them decoupled from the application's initialization logic.

---

## How to Extend the Engine: Creating New Components

This is the core strength of the engine. Follow these steps to create and integrate a new piece of logic.

### Step 1: Create the Step Class

Create a new Python file in `src/services/pipeline/steps/`. Your class must inherit from `PipelineStep` and implement its four required properties/methods.

**Example: A New Synchronous Step**
This step simply validates data. It's fast and doesn't need to be async.

```python
# src/services/pipeline/steps/data_validation_step.py
from .base_step import PipelineStep
from src.domain.models import TurnContext
from src.services.pipeline.resource_provider import ResourceProvider

class DataValidationStep(PipelineStep):
    @property
    def name(self) -> str:
        return "data_validation"

    def get_required_inputs(self) -> list[str]:
        return ["user_message"] # Needs the user's message

    def get_outputs(self) -> list[str]:
        return ["is_message_valid"] # Produces a boolean

    async def execute(self, context: TurnContext, resources: ResourceProvider) -> TurnContext:
        context.log(f"Executing step: {self.name}")
        message = context.get("user_message", "")
        
        # Simple validation logic
        is_valid = len(message) > 5
        
        context.set("is_message_valid", is_valid)
        context.log(f"Validation result: {is_valid}")
        return context
```

### Step 2: Register the Step

Open `src/services/pipeline/steps/__init__.py` and add your new class to the `ALL_STEPS` dictionary. This makes the orchestrator aware of it.

```python
# src/services/pipeline/steps/__init__.py
from .parallel_analysis_step import ParallelAnalysisStep
from .data_validation_step import DataValidationStep # <-- Import your new step

ALL_STEPS = {
    "parallel_analysis": ParallelAnalysisStep(),
    "data_validation": DataValidationStep(), # <-- Add it to the dictionary
    # ... other steps
}
```

### Step 3: Add the Step to the Workflow

Open `src/services/pipeline/workflows/standard_workflow.yaml` and add your new step to the `steps` list. Define its dependencies.

```yaml
# src/services/pipeline/workflows/standard_workflow.yaml
steps:
  - name: "parallel_analysis"
    # No dependencies, runs first

  - name: "data_validation"
    # Also has no dependencies, so it can run IN PARALLEL with parallel_analysis

  - name: "strategist"
    # This step now depends on BOTH of the previous steps
    dependencies: ["parallel_analysis", "data_validation"]
```
The engine will now automatically run your new validation step in parallel with the initial LLM call and ensure both are complete before the strategist runs.

---

### Advanced Component Examples

**1. A Step that Fetches from a Database (Async):**

This pattern is for steps that need to perform I/O, like querying MongoDB. The `execute` method is `async`.

```python
# src/services/pipeline/steps/memory_fetcher_step.py
class MemoryFetcherStep(PipelineStep):
    # ... name, inputs, outputs ...
    async def execute(self, context: TurnContext, resources: ResourceProvider) -> TurnContext:
        session_id = context.get("session_id")
        
        # 1. Get the database manager from the resource provider
        db = resources.get_db_manager()
        
        # 2. Perform an async database call
        memories = await db.get_memory_nodes_for_topic(session_id, "some_topic")
        
        # 3. Save the result to the context
        context.set("fetched_memories", memories)
        return context
```

**2. A Step that Interacts with an External Service (e.g., Vector DB):**

This shows how you would integrate a completely new service.

**First, add the client to the `ResourceProvider`:**
```python
# src/services/pipeline/resource_provider.py
class ResourceProvider:
    def __init__(self, ..., vector_db_client: VectorDBClient):
        # ...
        self._vector_db_client = vector_db_client
    
    def get_vector_db(self) -> VectorDBClient:
        return self._vector_db_client
```

**Then, create the step that uses it:**
```python
# src/services/pipeline/steps/vector_search_step.py
class VectorSearchStep(PipelineStep):
    # ... name, inputs, outputs ...
    async def execute(self, context: TurnContext, resources: ResourceProvider) -> TurnContext:
        query_embedding = context.get("user_message_embedding") # Assumes a previous step created this
        
        # 1. Get the new client from the resource provider
        vector_db = resources.get_vector_db()
        
        # 2. Perform the async search
        search_results = await vector_db.search(query_embedding)
        
        # 3. Save the result
        context.set("similar_docs", search_results)
        return context
```

By following this component-based pattern, you can build pipelines of arbitrary complexity, combining LLM calls, database queries, and custom business logic with ease.