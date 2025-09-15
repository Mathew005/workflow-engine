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
from src.domain.lifecycle import StepLifecycle

st.set_page_config(layout="wide", page_title="LangGraph AI Workflow Engine")

@st.cache_resource
def initialize_base_resources():
    st.write("[INFO] Initializing base resources (DB Manager)...")
    return ResourceProvider(db_manager=DatabaseManager(settings.mongo_uri))

@st.cache_data
def load_workflow_def(workflow_path: Path) -> dict:
    with open(workflow_path, 'r') as f:
        return yaml.safe_load(f)

def get_available_workflows(directory: str) -> Dict[str, Path]:
    root_dir = Path(directory)
    workflows = {}
    if not root_dir.is_dir(): return {}
    for f in sorted(root_dir.glob("*/workflow.yaml")):
        workflow_name = f.parent.name
        workflows[workflow_name.replace("_", " ").title()] = f
    return workflows

async def run_and_render_workflow(
    resources: ResourceProvider,
    workflow_def: WorkflowDefinition,
    workflow_path: Path,
    initial_state: dict,
    dag_placeholder,
    log_placeholder,
    sub_dag_placeholder # <-- NEW: Dedicated placeholder for sub-dags
):
    st.session_state.debug_records = []
    st.session_state.sub_dags = {}
    
    workflow_dict = workflow_def.model_dump(exclude_none=True)
    step_names = {step['name'] for step in workflow_dict.get('steps', [])}
    st.session_state.step_lifecycle = {name: StepLifecycle.PENDING.value for name in step_names}
    dag_placeholder.graphviz_chart(generate_dag_image(workflow_dict, st.session_state.step_lifecycle))

    full_initial_state = {"workflow_data": initial_state, "execution_log": [], "debug_log": [], "error_info": [], "step_lifecycle": st.session_state.step_lifecycle}

    with st.status("Executing workflow...", expanded=True) as status:
        async for event in run_workflow_streaming(resources, workflow_dict, workflow_path, full_initial_state):
            if event["type"] == "lifecycle_update":
                update_data = event["data"]
                st.session_state.step_lifecycle[update_data["step_name"]] = update_data["status"]
                dag_placeholder.graphviz_chart(generate_dag_image(workflow_dict, st.session_state.step_lifecycle))
                await asyncio.sleep(0.01)

            elif event["type"] == "log":
                record = event["data"]
                st.session_state.debug_records.append(record)
                with log_placeholder.container():
                    st.subheader("Live Execution Log")
                    display_debug_log(st.session_state.debug_records, workflow_dict)
                await asyncio.sleep(0.01)

            elif event["type"] == "sub_workflow_event":
                data = event["data"]
                parent_step, sub_workflow_name = data["parent_step"], data["sub_workflow"]
                original_event = data["original_event"]
                
                if parent_step not in st.session_state.sub_dags:
                    sub_workflow_yaml_path = workflow_path.parent.parent / sub_workflow_name / "workflow.yaml"
                    sub_workflow_dict = load_workflow_def(sub_workflow_yaml_path)
                    sub_step_names = {step['name'] for step in sub_workflow_dict.get('steps', [])}
                    
                    # Use the dedicated placeholder for the expander
                    with sub_dag_placeholder.container():
                        expander = st.expander(f"Sub-Workflow Execution: `{parent_step}` (`{sub_workflow_name}`)", expanded=True)
                    
                    st.session_state.sub_dags[parent_step] = {
                        "dict": sub_workflow_dict,
                        "lifecycle": {name: StepLifecycle.PENDING.value for name in sub_step_names},
                        "placeholder": expander.empty() # Placeholder inside the expander
                    }
                
                sub_dag_state = st.session_state.sub_dags[parent_step]
                original_event_type = original_event["event"]

                if original_event_type == "on_chain_start" and original_event["name"] != "__root__":
                    sub_dag_state["lifecycle"][original_event["name"]] = "RUNNING"
                
                elif original_event_type == "on_chain_end":
                    node_output = original_event["data"].get("output", {})
                    if isinstance(node_output, dict) and "debug_log" in node_output and node_output["debug_log"]:
                        log_data = node_output["debug_log"][0]
                        sub_dag_state["lifecycle"][log_data["step_name"]] = log_data["status"].upper()
                
                sub_dag_state["placeholder"].graphviz_chart(generate_dag_image(sub_dag_state["dict"], sub_dag_state["lifecycle"]))
                await asyncio.sleep(0.01)

            elif event["type"] == "result":
                st.session_state.last_run_state = event["data"]
                final_state = event["data"]
                if final_state.get("error_info"): status.update(label="Workflow failed!", state="error")
                else: status.update(label="Workflow complete!", state="complete")

def display_debug_log(debug_records, workflow_def: dict):
    steps_config = {step['name']: step for step in workflow_def.get('steps', [])}
    for record in debug_records:
        step_name, status, color = record.get('step_name', 'Unknown'), record.get('status', 'Unknown'), "grey"
        if status == "Completed": color = "green"
        if status == "Running": color = "orange"
        if status == "Failed": color = "red"
        with st.expander(f":{color}[●] **{step_name}** (`{record.get('type')}`) - {record.get('duration_ms', 0):.2f} ms"):
            st.subheader("Data Flow")
            colA, colB = st.columns(2); colA.markdown("**Inputs**"); colA.json(record.get('inputs', {})); colB.markdown("**Outputs**"); colB.json(record.get('outputs', {}))
            if status == "Failed" and "error" in record:
                st.subheader(":red[Error Details]"); st.error(record["error"].get("message", "No message."));
                with st.expander("Show Traceback"): st.code(record["error"].get("traceback", "No traceback."), language="text")
            st.subheader("Node Configuration (from YAML)"); st.json(steps_config.get(step_name, {}).get('params', {}))

st.title("Declarative AI Workflow Engine (Powered by LangGraph)")
resources = initialize_base_resources()
if 'current_workflow_name' not in st.session_state: st.session_state.current_workflow_name = None
col1, col2 = st.columns([1, 2])
with col1:
    st.subheader("Workflow Configuration")
    workflow_dir = "src/services/pipeline/workflows"
    available_workflows = get_available_workflows(workflow_dir)
    if not available_workflows: st.error(f"No workflow packages found in `{workflow_dir}`."); st.stop()
    selected_workflow_name = st.selectbox("Choose a workflow:", options=list(available_workflows.keys()))
    if st.session_state.current_workflow_name != selected_workflow_name:
        st.session_state.current_workflow_name = selected_workflow_name
        st.session_state.step_lifecycle = {}; st.session_state.debug_records = []; st.session_state.last_run_state = None; st.session_state.sub_dags = {}
    workflow_path = available_workflows[selected_workflow_name]
    with open(workflow_path, 'r') as f: workflow_text = f.read()
    try:
        workflow_dict = yaml.safe_load(workflow_text)
        workflow_def = WorkflowDefinition.model_validate(workflow_dict)
        st.subheader("Execution Plan (DAG)")
        dag_placeholder = st.empty()
        dag_placeholder.graphviz_chart(generate_dag_image(workflow_def.model_dump(exclude_none=True), st.session_state.get('step_lifecycle')))
        st.info(f"**Description:** {workflow_def.description}")
    except (yaml.YAMLError, ValidationError) as e:
        st.error(f"Invalid workflow YAML in {workflow_path.name}:"); st.exception(e); st.stop()
with col2:
    st.subheader("Pipeline Inputs")
    initial_ui_state = {}
    for wf_input in workflow_def.inputs:
        input_name, input_type, label = wf_input.name, wf_input.type, wf_input.label
        if input_type == "text": initial_ui_state[input_name] = st.text_input(label, value=wf_input.default or "")
        elif input_type == "file":
            uploaded_file = st.file_uploader(label, type=["png", "jpg", "jpeg", "pdf"])
            initial_ui_state[input_name] = {"data": uploaded_file.getvalue(), "mime_type": uploaded_file.type} if uploaded_file else None
    
    # Create the two placeholders for logs and sub-dags
    log_placeholder = st.empty()
    sub_dag_placeholder = st.empty()
    
    if st.button("Run Pipeline", type="primary"):
        if any(i.type == "file" and not initial_ui_state.get(i.name) for i in workflow_def.inputs): st.error("A required file is not uploaded.")
        else:
            # Clear placeholders and state before a new run
            log_placeholder.empty()
            sub_dag_placeholder.empty()
            st.session_state.sub_dags = {}
            try:
                asyncio.run(run_and_render_workflow(resources, workflow_def, workflow_path, initial_ui_state, dag_placeholder, log_placeholder, sub_dag_placeholder))
            except Exception as e: st.error(f"An unexpected error occurred: {e}"); st.exception(e)

st.divider()
if 'last_run_state' in st.session_state and isinstance(st.session_state.last_run_state, dict):
    st.subheader("Pipeline Results")
    final_run_state = st.session_state.last_run_state
    tab1, tab2, tab3 = st.tabs(["Final State", "Execution Summary", "Lifecycle Log"])
    with tab1:
        try: st.json(final_run_state.get("workflow_data", {}))
        except TypeError as e: st.error(f"Could not display final state. Error: {e}"); st.write(final_run_state)
    with tab2:
        log_items = final_run_state.get("execution_log", [])
        if isinstance(log_items, list): st.code("\n".join(map(str, log_items)), language="text")
        else: st.warning("Execution log not in expected format."); st.write(log_items)
    with tab3: st.json(final_run_state.get("step_lifecycle", {}))