import streamlit as st
import asyncio
import yaml
from typing import Dict, Any
from pathlib import Path

import nest_asyncio
nest_asyncio.apply()

from src.config.settings import settings
from src.data_layer.database_manager import DatabaseManager
from src.services.pipeline.resource_provider import ResourceProvider
from src.services.dag_renderer import generate_dag_image
from src.services.workflow_orchestrator import run_workflow_streaming

st.set_page_config(layout="wide", page_title="LangGraph AI Workflow Engine")

@st.cache_resource
def initialize_base_resources():
    """Initializes and caches non-async-sensitive resources."""
    st.write("[INFO] Initializing base resources (DB Manager)...")
    return ResourceProvider(db_manager=DatabaseManager(settings.mongo_uri))

def get_available_workflows(directory: str) -> Dict[str, Path]:
    """Scans a directory for workflow YAML files."""
    workflow_dir = Path(directory)
    if not workflow_dir.is_dir(): return {}
    return {f.stem.replace("_", " ").title(): f for f in sorted(workflow_dir.glob("*.yaml"))}

async def run_and_render_workflow(resources: ResourceProvider, workflow_def: dict, initial_state: dict):
    """Calls the orchestrator and renders UI updates based on yielded events."""
    st.subheader("Live Execution Log")
    log_placeholder = st.empty()
    st.session_state.debug_records = []
    
    with st.status("Executing workflow...", expanded=True) as status:
        async for event in run_workflow_streaming(resources, workflow_def, initial_state):
            if event["type"] == "log":
                record = event["data"]
                st.session_state.debug_records.append(record)
                with log_placeholder.container():
                    display_debug_log(st.session_state.debug_records, workflow_def)
                await asyncio.sleep(0.01)  # Yield to allow UI to refresh
            
            elif event["type"] == "result":
                st.session_state.last_run_state = event["data"]
                status.update(label="Workflow complete!", state="complete")

def display_debug_log(debug_records, workflow_def):
    """Renders the structured debug log."""
    steps_config = {step['name']: step for step in workflow_def.get('steps', [])}
    for record in debug_records:
        step_name = record.get('step_name', 'Unknown')
        color = "green" if record.get('status') == "Completed" else "orange"
        with st.expander(f":{color}[●] **{step_name}** (`{record.get('type')}`) - {record.get('duration_ms', 0):.2f} ms"):
            st.subheader("Data Flow")
            colA, colB = st.columns(2)
            colA.markdown("**Inputs**"); colA.json(record.get('inputs', {}))
            colB.markdown("**Outputs**"); colB.json(record.get('outputs', {}))
            st.subheader("Node Configuration (from YAML)")
            st.json(steps_config.get(step_name, {}).get('params', {}))

# --- UI Layer --- #
st.title("Declarative AI Workflow Engine (Powered by LangGraph)")

resources = initialize_base_resources()

col1, col2 = st.columns([1, 2])
with col1:
    st.subheader("Workflow Configuration")
    workflow_dir = "src/services/pipeline/workflows"
    available_workflows = get_available_workflows(workflow_dir)
    
    if not available_workflows:
        st.error(f"No workflow YAML files found in `{workflow_dir}`.")
        st.stop()

    selected_workflow_name = st.selectbox("Choose a workflow:", options=list(available_workflows.keys()))
    workflow_path = available_workflows[selected_workflow_name]

    with open(workflow_path, 'r') as f: workflow_text = f.read()
    
    try:
        workflow_def = yaml.safe_load(workflow_text)
        st.subheader("Execution Plan (DAG)")
        st.graphviz_chart(generate_dag_image(workflow_def))
        st.info(f"**Description:** {workflow_def.get('description', 'No description.')}")
    except (yaml.YAMLError, KeyError) as e:
        st.error(f"Invalid YAML in {workflow_path.name}: {e}")
        st.stop()

with col2:
    st.subheader("Pipeline Inputs")
    initial_state = {"session_id": "test_session_123", "execution_log": [], "debug_log": []}
    
    for wf_input in workflow_def.get("inputs", []):
        input_name, input_type = wf_input["name"], wf_input["type"]
        label = wf_input.get("label", input_name)
        if input_type == "text":
            initial_state[input_name] = st.text_input(label, value=wf_input.get("default", ""))
        elif input_type == "file":
            uploaded_file = st.file_uploader(label, type=["png", "jpg", "jpeg", "pdf"])
            initial_state[input_name] = {"data": uploaded_file.getvalue(), "mime_type": uploaded_file.type} if uploaded_file else None

    if st.button("Run Pipeline", type="primary"):
        if any(i["type"] == "file" and not initial_state.get(i["name"]) for i in workflow_def.get("inputs", [])):
            st.error("A required file is not uploaded.")
        else:
            try:
                asyncio.run(run_and_render_workflow(resources, workflow_def, initial_state))
            except Exception as e:
                st.error(f"An unexpected error occurred during the workflow run: {e}")
                st.exception(e)

st.divider()

# --- Results Display Section --- #
if 'last_run_state' in st.session_state and isinstance(st.session_state.last_run_state, dict):
    st.subheader("Pipeline Results")
    final_run_state = st.session_state.last_run_state
    
    tab1, tab2 = st.tabs(["Final State", "Execution Summary"])
    
    with tab1:
        try:
            display_state = {k: v for k, v in final_run_state.items() if not k.startswith('__') and k != 'debug_log'}
            st.json(display_state)
        except TypeError as e:
            st.error(f"Could not display final state. It may contain non-serializable data. Error: {e}")
            st.write(display_state)

    with tab2:
        log_items = final_run_state.get("execution_log", [])
        if isinstance(log_items, list):
            log_text = "\n".join(map(str, log_items))
            st.code(log_text, language="text")
        else:
            st.warning("Execution log is not in the expected format (list of strings).")
            st.write(log_items)