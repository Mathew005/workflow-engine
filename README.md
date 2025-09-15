# Declarative AI Workflow Engine

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Built%20with-green)](https://python.langchain.com/docs/langgraph)
[![Streamlit](https://img.shields.io/badge/Streamlit-UI-red)](https://streamlit.io/)
[![Gemini API](https://img.shields.io/badge/Google-Gemini%20API-blue)](https://ai.google.dev/)

This project is a powerful, declarative AI workflow engine built on LangGraph. It enables developers to define complex, multi-step AI and business logic pipelines using simple YAML files. The engine is designed to be highly extensible, allowing for the creation of reusable components (sub-workflows) and custom Python code nodes for maximum flexibility.

The entire system is observable through a Streamlit web interface, providing real-time execution logs, data flow visualization, and a clear view of the Directed Acyclic Graph (DAG) for any given workflow.

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
    ├── domain/
    │   └── workflow_schema.py # Pydantic models for YAML validation
    ├── llm_integration/
    │   └── gemini_client.py    # Resilient client for Google Gemini
    └── services/
        ├── custom_code/
        │   ├── base.py           # Abstract base class for all custom nodes
        │   ├── __init__.py       # Auto-discovery script for custom nodes
        │   └── steps/            # <-- YOUR custom Python nodes go here
        │       ├── data_enrichment.py
        │       └── data_extraction.py
        ├── dag_renderer.py       # Logic for visualizing the workflow graph
        ├── langgraph_builder.py  # Core engine: builds and compiles LangGraph graphs
        ├── pipeline/
        │   └── workflows/        # <-- YOUR workflow packages go here
        │       ├── extract_contact_details/
        │       │   ├── prompts/
        │       │   │   └── 1_extract_info.txt
        │       │   └── workflow.yaml
        │       ├── enrich_company_profile/
        │       │   └── workflow.yaml
        │       └── qualify_sales_lead/ # A master workflow example
        │           ├── prompts/
        │           │   └── 1_score_lead.txt
        │           └── workflow.yaml
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
It is highly recommended to use a virtual environment.```bash
python3 -m venv venv
source venv/bin/activate
```

#### 4. Install Dependencies
*(You may need to create a `requirements.txt` file from your installed packages)*
```bash
pip install streamlit google-generativeai pydantic pydantic-settings pymongo graphviz langchain-core langgraph```

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

# Your MongoDB connection string (currently used as a placeholder)
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

A simple workflow might take a user's message and use an LLM to analyze it.

**Step 1: Create the Workflow Package Directory**

Inside `src/services/pipeline/workflows/`, create a new directory for your workflow. The directory name will be its unique identifier.

```
src/services/pipeline/workflows/
└── sentiment_analyzer/          <-- New directory
    └── prompts/                 <-- Prompts subdirectory
```

**Step 2: Write the `workflow.yaml`**

Create a `workflow.yaml` file inside your new directory.

**`src/services/pipeline/workflows/sentiment_analyzer/workflow.yaml`**
```yaml
name: "Sentiment Analyzer"
description: "A simple workflow that analyzes the sentiment of a user's message."

# Declare the inputs this workflow requires to start.
# The UI will automatically generate form fields for these.
inputs:
  - name: "user_text"
    type: "text"
    label: "Enter text to analyze:"
    default: "I am so happy with the new update, it's fantastic!"

# Define the sequence of steps.
steps:
  - name: "analyze_sentiment_llm"
    type: "llm"       # This is a Large Language Model step.
    dependencies: []  # No dependencies, so it runs at the start.
    params:
      prompt_template: "1_sentiment.txt" # The prompt file to use.
      # Map the workflow's 'user_text' input to the prompt's '<message_to_analyze>' placeholder.
      input_mapping:
        message_to_analyze: "user_text"
      # The result of this step will be stored in the state under this key.
      output_key: "sentiment_result"
```

**Step 3: Write the Prompt Template**

Inside the `prompts/` directory, create the prompt file referenced in your YAML.

**`src/services/pipeline/workflows/sentiment_analyzer/prompts/1_sentiment.txt`**
```
# ROLE
You are a sentiment analysis expert.

# TASK
Analyze the sentiment of the following user message. Your entire output must be a single, valid JSON object. The sentiment must be one of: POSITIVE, NEGATIVE, NEUTRAL.

# USER MESSAGE
<message_to_analyze>

# OUTPUT SCHEMA
{
  "sentiment": "string",
  "confidence_score": "number (0.0 to 1.0)"
}
```

**Step 4: Run it!**
Save your files and refresh the Streamlit application in your browser. Your new "Sentiment Analyzer" workflow will now appear in the dropdown menu, ready to run.

### Tutorial 2: Creating a Custom Code Node

Custom nodes allow you to run any Python code. Let's create a node that validates the length of a message.

**Step 1: Create the Python File**

Inside `src/services/custom_code/steps/`, create a new file. The filename becomes part of the node's namespace.

**`src/services/custom_code/steps/text_validators.py`**

**Step 2: Write the Custom Step Class**

In your new file, write a class that inherits from `BaseCustomStep` and implements the required contract.

```python
from pydantic import BaseModel
from src.services.custom_code.base import BaseCustomStep

# 1. Define the Input Schema using Pydantic
# The engine will automatically validate that the input data matches this shape.
class IsTextTooShortInput(BaseModel):
    text_to_validate: str
    min_length: int = 5

# 2. Define the Output Schema using Pydantic
# The engine will use this to structure the output.
class IsTextTooShortOutput(BaseModel):
    is_valid: bool
    length: int

# 3. Implement the Step Class
class IsTextTooShortStep(BaseCustomStep):
    # Link the schemas to the class
    InputModel = IsTextTooShortInput
    OutputModel = IsTextTooShortOutput

    # The core logic goes in the 'execute' method
    async def execute(self, input_data: IsTextTooShortInput) -> IsTextTooShortOutput:
        current_length = len(input_data.text_to_validate or "")
        is_valid = current_length >= input_data.min_length
        
        return IsTextTooShortOutput(is_valid=is_valid, length=current_length)
```The engine will automatically discover this class and register it as `text_validators.IsTextTooShortStep`.

**Step 3: Use the Custom Node in a Workflow**

You can now use this node in any `workflow.yaml` file.

```yaml
steps:
  - name: "validate_message_length"
    type: "code"  # This is a Custom Code Node step.
    dependencies: []
    params:
      # The name is <filename>.<ClassName>
      function_name: "text_validators.IsTextTooShortStep"
      # The value from this state key will be passed as the FIRST field
      # in the InputModel (i.e., 'text_to_validate').
      input_key: "user_text"
      output_key: "validation_output"
```

### Tutorial 3: Creating a Master Workflow (Sub-Workflows)

Master workflows compose other workflows. Let's use our `sentiment_analyzer` and `text_validators` to create a master workflow.

**Step 1: Create a New Master Workflow Package**

Create a new workflow package directory, e.g., `src/services/pipeline/workflows/validation_and_analysis/`.

**Step 2: Write the Master `workflow.yaml`**

This YAML will define steps with `type: workflow`.

**`src/services/pipeline/workflows/validation_and_analysis/workflow.yaml`**
```yaml
name: "Validation and Analysis Orchestrator"
description: "A master workflow that validates input text before analyzing its sentiment."

inputs:
  - name: "master_input_text"
    type: "text"
    label: "Enter text to validate and analyze:"

steps:
  - name: "run_validation"
    type: "code" # We can mix and match step types
    dependencies: []
    params:
      function_name: "text_validators.IsTextTooShortStep"
      input_key: "master_input_text"
      output_key: "validation_result" # Output will be e.g., {"is_valid": true, "length": 25}

  - name: "run_sentiment_analysis"
    type: "workflow" # This step calls another workflow.
    dependencies:
      - "validation_result" # This step will ONLY run if 'run_validation' is successful.
    params:
      # The directory name of the workflow to call.
      workflow_name: "sentiment_analyzer"
      # Map a key from the parent state to the required input of the sub-workflow.
      input_mapping:
        master_input_text: "user_text"
      # Map an output key from the sub-workflow's state back to the parent state.
      output_mapping:
        sentiment_result: "final_sentiment_analysis"
```