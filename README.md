# AI Workflow Engine

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Built%20with-green)](https://python.langchain.com/docs/langgraph)
[![Streamlit](https://img.shields.io/badge/Streamlit-UI-red)](https://streamlit.io/)
[![Gemini API](https://img.shields.io/badge/Google-Gemini%20API-blue)](https://ai.google.dev/)

This project lets you build and run multi-step AI and business tasks using simple YAML files. It uses a web interface to show you a live graph of your workflow as it runs, step-by-step.

## Features

*   **Define Workflows in YAML:** Create complex pipelines by defining steps in a human-readable format.
*   **Live Visualizations:** Watch your workflow's graph (DAG) update with colors in real-time as each step runs, succeeds, or fails.
*   **Run Custom Python Code:** Add your own Python logic as a step in any workflow. The system finds and integrates your code automatically.
*   **Reusable Workflows:** Call one workflow from another, allowing you to build complex systems from smaller, reusable parts.
*   **View Data Flow:** Check the inputs and outputs of every step in the web UI to easily debug your workflows.

## Project Structure

```text
workflow-engine-poc/
├── .env
├── .env.example
├── run.bat                 # Runner for Windows
├── run.sh                  # Runner for Mac/Linux
└── src/
    ├── app/streamlit_app.py
    ├── config/settings.py
    ├── data_layer/database_manager.py
    ├── domain/workflow_schema.py
    ├── llm_integration/gemini_client.py
    └── services/
        ├── custom_code/
        │   ├── base.py
        │   ├── __init__.py
        │   └── steps/            # <-- Add your custom Python files here
        ├── dag_renderer.py
        ├── langgraph_builder.py
        ├── pipeline/
        │   └── workflows/        # <-- Add your workflow folders here
        └── workflow_orchestrator.py```

## Setup

#### 1. Prerequisites
*   Python 3.10 or higher

#### 2. Get the Code
```bash
git clone <your-repository-url>
cd workflow-engine-poc
```

#### 3. Create a Virtual Environment
*On Mac/Linux:*
```bash
python3 -m venv venv
source venv/bin/activate
```
*On Windows:*
```bash
python -m venv venv
.\venv\Scripts\activate
```

#### 4. Install Dependencies
```bash
pip install streamlit google-generativeai pydantic pydantic-settings pymongo graphviz langchain-core langgraph nest-asyncio
```

#### 5. Set Up API Keys
Copy the example environment file.

```bash
cp .env.example .env
```
Open the new `.env` file and add your Google Gemini API Key. You can add more than one; the system will automatically use the next key if one hits a usage limit.

```ini
# .env
GEMINI_API_KEY="AIzaSy...YourFirstKey"
#GEMINI_API_KEY="AIzaSy...YourSecondKey"

MONGO_URI="mongodb://localhost:27017/"
```

## How to Run

*On Mac/Linux:*
```bash
bash run.sh
```

*On Windows:*
```bat
run.bat
```

Open your web browser and navigate to the local URL shown in your terminal.

---

## How to Build Workflows

### Part 1: Defining Steps in YAML

A workflow is a folder containing a `workflow.yaml` file and a `prompts` subfolder. The YAML file defines the inputs and steps.

This example runs two tasks at the same time (summarizing text and checking its quality) and then uses their results in a final step.

**File: `src/services/pipeline/workflows/1_Basic_Text_Analysis/workflow.yaml`**
```yaml
name: "1. Basic Text Analysis (Fan-Out, Fan-In)"
description: "Demonstrates parallel execution of LLM and Code steps, then joins their results."

# These are the inputs the workflow needs to start.
# The web UI will create a form for these.
inputs:
  - name: "text_input"
    type: "text"
    label: "Enter a block of text to analyze:"

# These are the steps in the workflow.
steps:
  - name: "summarize_text_llm"
    type: "llm"       # This step uses a Large Language Model.
    dependencies: []  # It has no dependencies, so it runs first.
    params:
      prompt_template: "1_summarize.txt"
      # Data mapping: The workflow's 'text_input' is sent to the prompt.
      input_mapping:
        text_to_summarize: "text_input"
      # The LLM's JSON output is saved as 'summary_result'.
      output_key: "summary_result"

  - name: "check_text_quality_code"
    type: "code"      # This step runs custom Python code.
    dependencies: []  # It also has no dependencies, so it runs in parallel.
    params:
      function_name: "text_processing.CheckTextQualityStep"
      input_mapping:
        text: "text_input"
      output_key: "quality_stats_result"

  - name: "synthesize_report_llm"
    type: "llm"
    # This step will only run after BOTH of its dependencies are finished.
    dependencies:
      - "summary_result"
      - "quality_stats_result"
    params:
      prompt_template: "2_synthesize_report.txt"
      # It uses the outputs from the previous steps as its input.
      input_mapping:
        summary: "summary_result"
        statistics: "quality_stats_result"
      output_key: "final_report"
```

### Part 2: Adding Custom Python Code

You can add your own Python code as a workflow step. The system automatically finds any class in the `src/services/custom_code/steps/` directory that is set up correctly.

**File: `src/services/custom_code/steps/text_processing.py`**

```python
from pydantic import BaseModel
from src.services.custom_code.base import BaseCustomStep

# 1. Define the exact inputs the class needs.
class CheckTextQualityInput(BaseModel):
    text: str

# 2. Define the exact outputs the class will produce.
class CheckTextQualityOutput(BaseModel):
    word_count: int
    average_word_length: float

# 3. Create the class. The system will find it automatically.
class CheckTextQualityStep(BaseCustomStep):
    InputModel = CheckTextQualityInput
    OutputModel = CheckTextQualityOutput

    # The main logic of your step goes here.
    async def execute(self, input_data: CheckTextQualityInput) -> CheckTextQualityOutput:
        words = input_data.text.lower().split()
        word_count = len(words)
        
        if word_count == 0:
            return CheckTextQualityOutput(word_count=0, average_word_length=0)

        avg_length = sum(len(word) for word in words) / word_count
        
        return CheckTextQualityOutput(
            word_count=word_count,
            average_word_length=round(avg_length, 2)
        )
```
To use this in a workflow, you refer to it by its filename and class name: `text_processing.CheckTextQualityStep`.

### Part 3: Calling a Workflow from Another Workflow

You can treat an entire workflow as a single step inside another workflow. This lets you build complex systems out of simple, reusable parts.

**File: `src/services/pipeline/workflows/3_Orchestrator_With_Sub_Workflow/workflow.yaml`**
```yaml
name: "3. Orchestrator with Sub-Workflow"
description: "Calls the 'Basic Text Analysis' workflow as a single step."

inputs:
  - name: "customer_review_text"
    type: "text"
    label: "Enter a customer review:"

steps:
  - name: "translate_input_llm"
    type: "llm"
    params:
      # ... (omitted for brevity)
      output_key: "translated_text" # This step outputs JSON like {"english_translation": "..."}

  - name: "run_text_analysis_sub_workflow"
    type: "workflow" # This step's type is 'workflow'.
    dependencies:
      - "translated_text" # It waits for the translation step to finish.
    params:
      # The folder name of the workflow you want to run.
      workflow_name: "1_Basic_Text_Analysis"
      
      # Map data FROM the orchestrator TO the sub-workflow's input.
      # It takes the 'english_translation' value from the 'translated_text' output
      # and provides it as the 'text_input' for the sub-workflow.
      input_mapping:
        translated_text.english_translation: "text_input"
        
      # Map data FROM the sub-workflow's output BACK to the orchestrator.
      # It takes the 'final_report' from the sub-workflow and saves it
      # as 'analysis_report' in this orchestrator's state.
      output_mapping:
        final_report: "analysis_report"
```