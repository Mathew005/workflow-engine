# Declarative AI Workflow Engine

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Built%20with-green)](https://python.langchain.com/docs/langgraph)
[![Streamlit](https://img.shields.io/badge/Streamlit-UI-red)](https://streamlit.io/)
[![Gemini API](https://img.shields.io/badge/Google-Gemini%20API-blue)](https://ai.google.dev/)

This project is a powerful, declarative AI workflow engine that lets you build and run complex, multi-step tasks using simple YAML files. It uses a Streamlit web interface to provide a live, color-coded graph visualization of your workflow as it executes step-by-step.

## Features

*   **Declarative YAML Workflows:** Define complex logic, dependencies, and data flow in a human-readable format.
*   **Live Visualizations:** Watch your workflow's graph (DAG) and sub-workflows update in real-time as each step runs, succeeds, or fails.
*   **Custom Python Nodes:** Inject your own Python code as a step in any workflow. The engine automatically discovers and integrates your code.
*   **Reusable Workflows (Composition):** Call one workflow from another, allowing you to build complex systems from smaller, reusable parts.
*   **Conditional Logic (Branching):** Create workflows that make decisions and take different paths based on data, using a `conditional_router`.
*   **Dynamic Mapping (Fan-Out):** Run a step in parallel for each item in a list, enabling powerful batch processing.
*   **Multimodal Inputs:** Use files (images, PDFs) as inputs to your workflows for tasks like image analysis or document processing.

## DAG Visualization

![Run](https://github.com/user-attachments/assets/c1908375-d984-4040-8547-26305c8bb30e)

## Project Structure

```text
workflow-engine-poc/
├── .env
├── .env.example
├── run.bat                 # Runner for Windows
├── run.sh                  # Runner for Mac/Linux
└── src/
    ├── app/streamlit_app.py
    ├── custom_code/
    │   ├── base.py
    │   ├── __init__.py
    │   └── steps/            # <-- Add your custom Python files here
    │       ├── content_processing.py
    │       ├── image_processing.py
    │       └── text_analysis.py
    ├── services/             # Core engine logic
    ├── shared_prompts/       # <-- Add reusable LLM prompts here
    └── workflows/            # <-- Add your workflow packages here
        ├── 1_Basic_Features_Demo/
        ├── 2_Graph_Structures_Demo/
        ├── 3_Advanced_Logic_Demo/
        ├── 4_Master_Orchestrator_Demo/
        └── 5_Multimodal_Analysis/```

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
pip install streamlit google-generativeai pydantic pydantic-settings graphviz langchain-core langgraph nest-asyncio httpx
```

#### 5. Set Up API Keys
Copy the example environment file.

```bash
cp .env.example .env
```
Open the new `.env` file and add your Google Gemini API Key(s).

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

## Developer Guide: A Tour of the Showcase Workflows

The best way to understand the engine is to explore the included showcase workflows. Each one is designed to demonstrate a specific set of features, building from the basics to the most advanced capabilities.

### Part 1: The Basics (`1_Basic_Features_Demo`)

This workflow demonstrates the three fundamental step types in a simple sequence: `llm`, `code`, and `api`.

**`src/workflows/1_Basic_Features_Demo/workflow.yaml`**
```yaml
steps:
  - name: "generate_article_idea"
    type: "llm"       # 1. An LLM call to generate content.
    dependencies: []
    params:
      prompt_template: "1_generate_idea.txt"
      input_mapping: { topic: "topic" }
      output_key: "article_idea"

  - name: "validate_title_length"
    type: "code"      # 2. A custom Python node to perform business logic.
    dependencies:
      - "article_idea"
    params:
      function_name: "content_processing.ValidateTitleStep"
      input_mapping: { title: "article_idea.title" }
      output_key: "title_validation"

  - name: "fetch_related_post"
    type: "api"       # 3. An external API call to fetch data.
    dependencies:
      - "title_validation"
    params:
      method: "GET"
      endpoint: "https://jsonplaceholder.typicode.com/posts/1"
      output_key: "related_post_data"
```

### Part 2: Graph Structures (`2_Graph_Structures_Demo`)

This workflow showcases parallel execution (fan-out) where three steps run simultaneously, followed by a synchronization step (fan-in) that waits for all of them to complete. It also uses a prompt from the `shared_prompts` directory.

**`src/workflows/2_Graph_Structures_Demo/workflow.yaml`**
```yaml
steps:
  # These three steps have no dependencies, so they run in parallel.
  - name: "analyze_sentiment"
    type: "llm"
    params:
      prompt_template: "analyze_sentiment.txt" # Uses a shared prompt
      # ...

  - name: "extract_hashtags"
    type: "llm"
    # ...

  - name: "get_text_statistics"
    type: "code"
    # ...

  # This step will only run after the three steps above have all finished.
  - name: "synthesize_engagement_report"
    type: "llm"
    dependencies:
      - "sentiment_result"
      - "hashtags_result"
      - "stats_result"
    # ...
    ```

### Part 3: Advanced Logic (`3_Advanced_Logic_Demo`)

This workflow demonstrates the engine's most powerful logic features:
1.  **Dynamic Mapping:** The `get_length_of_each_title` step runs a custom code node in parallel for each item in the input list.
2.  **Conditional Routing:** The `content_strategy_router` step makes a decision based on the data and directs the workflow down one of two different branches.

**`src/workflows/3_Advanced_Logic_Demo/workflow.yaml`**
```yaml
steps:
  - name: "get_length_of_each_title"
    type: "code"
    params:
      map_input: "article_titles" # 1. Fan-out over this list
      function_name: "content_processing.ValidateTitleStep"
      input_mapping:
        title: "item" # 'item' refers to each element in the mapped list
      output_key: "title_lengths"

  - name: "calculate_average_length"
    type: "code"
    dependencies: ["title_lengths"]
    # ...
    output_key: "average_analysis"

  - name: "content_strategy_router"
    type: "conditional_router" # 2. A decision-making step
    dependencies: ["average_analysis"]
    params:
      condition_key: "average_analysis.decision"
      routing_map:
        "short": "suggest_expansions" # If decision is "short", go here.
        "long": "suggest_summaries"  # If decision is "long", go here.
  
  - name: "suggest_expansions"
    type: "llm" # This is one branch.
    # ...
  
  - name: "suggest_summaries"
    type: "llm" # This is the other branch.
    # ...
```

### Part 4: Composition & Multimodality (`4`, `5`, `6`)

These workflows showcase the final set of advanced features:
*   **`4_Master_Orchestrator_Demo`:** Demonstrates composition by using `type: "workflow"` to call other workflows as single, reusable steps.
*   **`5_Multimodal_Analysis`:** Shows how to use `type: "file"` to accept image uploads and process them with a multimodal LLM.
*   **`6_Advanced_Mapping_Demo`:** The ultimate showcase. It uses `map_input` on a `type: "workflow"` step to run an entire, complex sub-workflow in parallel for each item in a list, demonstrating the UI's unique ability to track multiple, indexed DAGs in real-time.