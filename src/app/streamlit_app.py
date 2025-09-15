import streamlit as st
import asyncio
import yaml
from typing import Dict, Any
from pathlib import Path
from pydantic import ValidationError

import nest_asyncio
nest_asyncio.apply()

from src.config.settings import settings
from src.data_layer.database_manager import DatabaseManager
from src.services.pipeline.resource_provider import ResourceProvider
from src.services.dag_renderer import generate_dag_image
from src.services.workflow_orchestrator import run_workflow_streaming
from src.domain.workflow_schema import WorkflowDefinition
# NEW import
from src.domain.lifecycle import StepLifecycle

st.set_page_config(layout="wide", page_title="LangGraph AI Workflow Engine")

@st.cache_resource
def initialize_base_resources():
    st.write("[INFO] Initializing base resources (DB Manager)...")
    return ResourceProvider(db_manager=DatabaseManager(settings.mongo_uri))

def get_available_workflows(directory: str) -> Dict[str, Path]:
    root_dir = Path(directory)
    workflows = {}
    if not root_dir.is_dir(): return {}
    for f in sorted(root_dir.glob("*/workflow.yaml")):
        workflow_name = f.parent.name
        workflows[workflow_name.replace("_", " ").title()] = f
    return workflows

async def run_and_render_workflow(resources: ResourceProvider, workflow_def: WorkflowDefinition, workflow_path: Path, initial_state: dict):
    st.subheader("Live Execution Log")
    log_placeholder = st.empty()
    st.session_state.debug_records = []
    
    workflow_dict = workflow_def.model_dump(exclude_none=True)

    # --- FIX: Initialize the step_lifecycle dictionary ---
    step_names = {step['name'] for step in workflow_dict.get('steps', [])}
    initial_lifecycle = {name: StepLifecycle.PENDING for name in step_names}

    full_initial_state = {
        "workflow_data": initial_state,
        "execution_log": [],
        "debug_log": [],
        "error_info": [],
        "step_lifecycle": initial_lifecycle, # Add to initial state
    }

    with st.status("Executing workflow...", expanded=True) as status:
        async for event in run_workflow_streaming(resources, workflow_dict, workflow_path, full_initial_state):
            if event["type"] == "log":
                record = event["data"]
                st.session_state.debug_records.append(record)
                with log_placeholder.container():
                    display_debug_log(st.session_state.debug_records, workflow_dict)
                await asyncio.sleep(0.01)
            
            elif event["type"] == "result":
                st.session_state.last_run_state = event["data"]
                final_state = event["data"]
                if final_state.get("error_info"):
                    status.update(label="Workflow failed!", state="error")
                    failed_step = final_state["error_info"][0].get("failed_step", "Unknown")
                    st.error(f"**Execution Halted:** The workflow was stopped due to a failure in step '{failed_step}'.")
                else:
                    status.update(label="Workflow complete!", state="complete")

def display_debug_log(debug_records, workflow_def: dict):
    steps_config = {step['name']: step for step in workflow_def.get('steps', [])}
    for record in debug_records:
        step_name = record.get('step_name', 'Unknown')
        status = record.get('status', 'Unknown')
        color = "grey"
        if status == "Completed": color = "green"
        if status == "Running": color = "orange"
        if status == "Failed": color = "red"
        with st.expander(f":{color}[●] **{step_name}** (`{record.get('type')}`) - {record.get('duration_ms', 0):.2f} ms"):
            st.subheader("Data Flow")
            colA, colB = st.columns(2)
            colA.markdown("**Inputs**"); colA.json(record.get('inputs', {}))
            colB.markdown("**Outputs**"); colB.json(record.get('outputs', {}))
            if status == "Failed" and "error" in record:
                st.subheader(":red[Error Details]")
                st.error(record["error"].get("message", "No error message provided."))
                with st.expander("Show Traceback"):
                    st.code(record["error"].get("traceback", "No traceback available."), language="text")
            st.subheader("Node Configuration (from YAML)")
            st.json(steps_config.get(step_name, {}).get('params', {}))

# --- (The rest of the UI Layer is unchanged) ---
st.title("Declarative AI Workflow Engine (Powered by LangGraph)")
resources = initialize_base_resources()
col1, col2 = st.columns([1, 2])
with col1:
    st.subheader("Workflow Configuration")
    workflow_dir = "src/services/pipeline/workflows"
    available_workflows = get_available_workflows(workflow_dir)
    if not available_workflows:
        st.error(f"No workflow packages found in `{workflow_dir}`.")
        st.stop()
    selected_workflow_name = st.selectbox("Choose a workflow:", options=list(available_workflows.keys()))
    workflow_path = available_workflows[selected_workflow_name]
    with open(workflow_path, 'r') as f: workflow_text = f.read()
    try:
        workflow_dict = yaml.safe_load(workflow_text)
        workflow_def = WorkflowDefinition.model_validate(workflow_dict)
        st.subheader("Execution Plan (DAG)")
        dag_dict = workflow_def.model_dump(exclude_none=True)
        st.graphviz_chart(generate_dag_image(dag_dict))
        st.info(f"**Description:** {workflow_def.description}")
    except (yaml.YAMLError, ValidationError) as e:
        st.error(f"Invalid workflow YAML in {workflow_path.name}:")
        st.exception(e)
        st.stop()
with col2:
    st.subheader("Pipeline Inputs")
    initial_ui_state = {}
    for wf_input in workflow_def.inputs:
        input_name, input_type = wf_input.name, wf_input.type
        label = wf_input.label
        if input_type == "text":
            initial_ui_state[input_name] = st.text_input(label, value=wf_input.default or "")
        elif input_type == "file":
            uploaded_file = st.file_uploader(label, type=["png", "jpg", "jpeg", "pdf"])
            initial_ui_state[input_name] = {"data": uploaded_file.getvalue(), "mime_type": uploaded_file.type} if uploaded_file else None
    if st.button("Run Pipeline", type="primary"):
        if any(i.type == "file" and not initial_ui_state.get(i.name) for i in workflow_def.inputs):
            st.error("A required file is not uploaded.")
        else:
            try:
                asyncio.run(run_and_render_workflow(resources, workflow_def, workflow_path, initial_ui_state))
            except Exception as e:
                st.error(f"An unexpected error occurred during the workflow run: {e}")
                st.exception(e)
st.divider()
if 'last_run_state' in st.session_state and isinstance(st.session_state.last_run_state, dict):
    st.subheader("Pipeline Results")
    final_run_state = st.session_state.last_run_state
    tab1, tab2, tab3 = st.tabs(["Final State", "Execution Summary", "Lifecycle Log"])
    with tab1:
        try:
            display_state = final_run_state.get("workflow_data", {})
            st.json(display_state)
        except TypeError as e:
            st.error(f"Could not display final state. Error: {e}")
            st.write(final_run_state)
    with tab2:
        log_items = final_run_state.get("execution_log", [])
        if isinstance(log_items, list):
            log_text = "\n".join(map(str, log_items))
            st.code(log_text, language="text")
        else:
            st.warning("Execution log is not in the expected format.")
            st.write(log_items)
    with tab3:
        st.json(final_run_state.get("step_lifecycle", {}))