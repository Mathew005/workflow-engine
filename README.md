# Declarative AI Workflow Engine

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Built%20with-green)](https://python.langchain.com/docs/langgraph)
[![Streamlit](https://img.shields.io/badge/Streamlit-UI-red)](https://streamlit.io/)
[![Gemini API](https://img.shields.io/badge/Google-Gemini%20API-blue)](https://ai.google.dev/)

This project is a powerful, declarative AI workflow engine built on LangGraph. It enables developers to define complex, multi-step AI and business logic pipelines using simple YAML files. The engine is designed to be highly extensible, allowing for the creation of reusable components (sub-workflows) and custom Python code nodes for maximum flexibility.

The entire system is observable through a Streamlit web interface, which provides:
*   Real-time, color-coded visualization of the main workflow's Directed Acyclic Graph (DAG) as it executes.
*   Dynamic, real-time rendering of sub-workflow DAGs when they are invoked.
*   Detailed execution logs, showing the data flowing in and out of each step.
*   Complete error reporting and tracebacks for easier debugging.

## Core Concepts

The engine is built on three fundamental concepts:

1.  **The Workflow Package:** A self-contained directory that represents a single, reusable workflow. It bundles the workflow's definition (`workflow.yaml`) with all of its required prompts, making it portable and easy to version.
2.  **The Custom Code Node:** A Python class that allows you to inject any custom logic into a workflow. These nodes are automatically discovered by the engine and are type-safe, using Pydantic for input and output validation. This is the bridge between your declarative YAML and your imperative Python code for tasks like database lookups, complex calculations, or third-party API calls.
3.  **The Master Workflow (Orchestrator):** A workflow that, instead of just running LLM or code steps, can call other workflows as if they were single nodes. This enables true composition, allowing you to build large, complex applications from smaller, tested, and reusable components.

## Project Structure

```text
workflow-engine-poc/
├── .gitignore
├── run.sh                  # Main execution script
└── src/
    ├── app/
    │   └── streamlit_app.py  # The Streamlit web UI
    ├── config/
    │   └── settings.py       # Pydantic settings management
    ├── data_layer/
    │   └── database_manager.py # Placeholder for DB connections
    ├── domain/
    │   ├── lifecycle.py      # Enum for step execution status
    │   ├── models.py         # Shared Pydantic models
    │   └── workflow_schema.py # Pydantic models for YAML validation
    ├── llm_integration/
    │   ├── gemini_client.py    # Resilient client for Google Gemini
    │   ├── key_manager.py      # Handles API key rotation
    │   └── prompt_loader.py    # Loads prompts from workflow packages
    └── services/
        ├── custom_code/
        │   ├── base.py           # Abstract base class for all custom nodes
        │   ├── __init__.py       # Auto-discovery script for custom nodes
        │   └── steps/            # <-- YOUR custom Python nodes go here
        │       ├── business_logic.py
        │       ├── image_processing.py
        │       ├── lead_processing.py
        │       └── text_processing.py
        ├── dag_renderer.py       # Logic for visualizing the workflow graph
        ├── langgraph_builder.py  # Core engine: builds and compiles LangGraph graphs
        ├── pipeline/
        │   └── workflows/        # <-- YOUR workflow packages go here
        │       ├── 1_Basic_Text_Analysis/
        │       │   ├── prompts/
        │       │   └── workflow.yaml
        │       ├── 2_Hybrid_Image_Analysis/
        │       ├── 3_Orchestrator_With_Sub_Workflow/
        │       ├── 4_Complex_Hybrid_Orchestrator/
        │       └── 5_Advanced_Lead_Processor/
        └── workflow_orchestrator.py # Manages the streaming execution of a workflow
```

## Setup & Installation

#### 1. Prerequisites
*   Python 3.10 or higher

#### 2. Clone the Repository
```bash
git clone <your-repository-url>
cd workflow-engine-poc
```

#### 3. Create a Virtual Environment
It is highly recommended to use a virtual environment.
```bash
python3 -m venv venv
source venv/bin/activate
```

#### 4. Install Dependencies
```bash
pip install streamlit google-generativeai pydantic pydantic-settings pymongo graphviz langchain-core langgraph nest-asyncio
```

#### 5. Set Up Environment Variables
Copy the example environment file and fill in your API key. The engine supports multiple keys for automatic rotation in case of rate limiting or quota issues.

```bash
cp .env.example .env
```
Now, open `.env` and add your Google Gemini API Key(s).
```ini
# .env

# The first active (uncommented) key will be used.
# The engine will automatically rotate to the next key if it encounters a quota error.
GEMINI_API_KEY="AIzaSy...YourFirstKey"
#GEMINI_API_KEY="AIzaSy...YourSecondKey"

# Your MongoDB connection string
MONGO_URI="mongodb://localhost:27017/"
```

## Running the Application

Simply execute the `run.sh` script, which will start the Streamlit web server.

```bash
bash run.sh
```
Navigate to the local URL provided by Streamlit in your browser to access the UI.

---

## Developer Guide: Building Your Own Workflows

### Tutorial 1: Creating a Simple Workflow

A simple workflow can perform multiple tasks in parallel. The `1_Basic_Text_Analysis` workflow, included in the project, demonstrates a "fan-out, fan-in" pattern where an LLM and a custom code node run simultaneously before their results are joined by a final step.

**Step 1: The `workflow.yaml`**

This file defines the structure, inputs, and steps of the workflow.

**`src/services/pipeline/workflows/1_Basic_Text_Analysis/workflow.yaml`**
```yaml
name: "1. Basic Text Analysis (Fan-Out, Fan-In)"
description: "Demonstrates parallel execution of LLM and Code steps, then joins their results."

# Declare the inputs this workflow requires to start.
# The UI will automatically generate form fields for these.
inputs:
  - name: "text_input"
    type: "text"
    label: "Enter a block of text to analyze:"
    default: "The new declarative workflow engine is incredibly powerful."

# Define the sequence of steps.
steps:
  - name: "summarize_text_llm"
    type: "llm"       # This is a Large Language Model step.
    dependencies: []  # No dependencies, so it runs at the start.
    params:
      prompt_template: "1_summarize.txt" # The prompt file to use.
      # Map the workflow's 'text_input' to the prompt's '<text_to_summarize>' placeholder.
      input_mapping:
        text_to_summarize: "text_input"
      # The result of this step will be stored in the state under this key.
      output_key: "summary_result"

  - name: "check_text_quality_code"
    type: "code"      # This is a custom code step.
    dependencies: []  # No dependencies, runs in parallel with the LLM step.
    params:
      function_name: "text_processing.CheckTextQualityStep"
      input_mapping:
        text: "text_input"
      output_key: "quality_stats_result"

  - name: "synthesize_report_llm"
    type: "llm"
    # This step depends on the outputs of the first two steps.
    # It will only run after BOTH 'summary_result' and 'quality_stats_result' are available.
    dependencies:
      - "summary_result"
      - "quality_stats_result"
    params:
      prompt_template: "2_synthesize_report.txt"
      input_mapping:
        summary: "summary_result"
        statistics: "quality_stats_result"
      output_key: "final_report"
```

**Step 2: The Prompt Template**

This is the prompt used by the `summarize_text_llm` step.

**`src/services/pipeline/workflows/1_Basic_Text_Analysis/prompts/1_summarize.txt`**
```
# TASK
Summarize the following text in a single, concise sentence.

# TEXT
<text_to_summarize>

# OUTPUT SCHEMA
Your entire output must be a single, valid JSON object.
{
  "summary": "string"
}
```

**Step 3: Run it!**
Save your files and refresh the Streamlit application. The "1 Basic Text Analysis..." workflow will be available in the dropdown, ready to run.

### Tutorial 2: Creating a Custom Code Node

Custom nodes allow you to run any Python code. The `check_text_quality_code` step from Tutorial 1 uses the `CheckTextQualityStep` node. Here's how it's built.

**Step 1: The Python File**

The file is located in `src/services/custom_code/steps/`. The filename (`text_processing`) becomes part of the node's namespace.

**`src/services/custom_code/steps/text_processing.py`**

**Step 2: The Custom Step Class**

The class inherits from `BaseCustomStep` and defines Pydantic models for type-safe inputs and outputs.

```python
from pydantic import BaseModel, Field
import re
from src.services.custom_code.base import BaseCustomStep

# 1. Define the Input Schema using Pydantic
# The engine will validate that the input data matches this shape.
class CheckTextQualityInput(BaseModel):
    text: str

# 2. Define the Output Schema using Pydantic
# The engine will use this to structure the output.
class CheckTextQualityOutput(BaseModel):
    word_count: int
    average_word_length: float = Field(..., description="Average length of words in the text.")

# 3. Implement the Step Class
class CheckTextQualityStep(BaseCustomStep):
    # Link the schemas to the class
    InputModel = CheckTextQualityInput
    OutputModel = CheckTextQualityOutput

    # The core logic goes in the 'execute' method
    async def execute(self, input_data: CheckTextQualityInput) -> CheckTextQualityOutput:
        words = re.findall(r'\b\w+\b', input_data.text.lower())
        word_count = len(words)
        
        if word_count == 0:
            return CheckTextQualityOutput(word_count=0, average_word_length=0)

        total_word_length = sum(len(word) for word in words)
        avg_length = total_word_length / word_count
        
        return CheckTextQualityOutput(
            word_count=word_count,
            average_word_length=round(avg_length, 2)
        )
```
The engine automatically discovers this class and registers it as `text_processing.CheckTextQualityStep`.

**Step 3: Using the Custom Node in a Workflow**

As seen in Tutorial 1, you use the node by referencing its `function_name` and mapping workflow state keys to its `InputModel` fields.

```yaml
steps:
  - name: "check_text_quality_code"
    type: "code"
    params:
      # The name is <filename>.<ClassName>
      function_name: "text_processing.CheckTextQualityStep"
      # Map keys from the workflow state to fields in the InputModel.
      # 'text_input' (from workflow) maps to 'text' (in CheckTextQualityInput)
      input_mapping:
        text: "text_input"
      output_key: "quality_stats_result"```

### Tutorial 3: Creating a Master Workflow (Sub-Workflows)

Master workflows compose other workflows. The `3_Orchestrator_With_Sub_Workflow` example calls the `1_Basic_Text_Analysis` workflow as a single step.

**The Master `workflow.yaml`**

This YAML defines a step with `type: workflow`, treating an entire workflow package as a reusable component.

**`src/services/pipeline/workflows/3_Orchestrator_With_Sub_Workflow/workflow.yaml`**
```yaml
name: "3. Orchestrator with Sub-Workflow"
description: "Demonstrates composing workflows by calling the 'Basic Text Analysis' workflow as a single step."

inputs:
  - name: "customer_review_text"
    type: "text"
    label: "Enter a customer review:"

steps:
  - name: "translate_input_llm"
    type: "llm"
    dependencies: []
    params:
      prompt_template: "1_translate.txt"
      input_mapping:
        text_to_translate: "customer_review_text"
      output_key: "translated_text" # Output: {"english_translation": "..."}

  - name: "run_text_analysis_sub_workflow"
    type: "workflow" # This step calls another workflow.
    dependencies:
      - "translated_text"
    params:
      # The directory name of the workflow to call.
      workflow_name: "1_Basic_Text_Analysis"
      
      # Map a key from the parent state to the required input of the sub-workflow.
      # The value of 'translated_text.english_translation' from the parent state
      # will be passed as the 'text_input' to the sub-workflow.
      input_mapping:
        translated_text.english_translation: "text_input"
        
      # Map an output key from the sub-workflow's state back to the parent state.
      # The 'final_report' from the sub-workflow is saved as 'analysis_report' here.
      output_mapping:
        final_report: "analysis_report"
  
  - name: "determine_final_action_code"
    type: "code"
    dependencies:
      - "analysis_report"
    params:
      function_name: "business_logic.DetermineFinalActionStep"
      input_mapping:
        report: "analysis_report"
      output_key: "final_action"
```