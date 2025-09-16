import streamlit as st
import asyncio
import yaml
import json
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

# --- UI HELPER FUNCTIONS ---

def is_image_url(data: Any) -> bool:
    return isinstance(data, str) and any(data.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp'])

def is_tabular(data: Any) -> bool:
    if not isinstance(data, list) or not data: return False
    if all(isinstance(item, dict) for item in data):
        return True if len(data) == 1 else all(set(data[0].keys()) == set(item.keys()) for item in data)
    return False

def render_output(output_key: str, output_data: Any, hints: Dict[str, str]):
    st.subheader(f"Output: `{output_key}`")
    hint = hints.get(output_key)
    
    render_data = output_data
    if isinstance(output_data, dict) and len(output_data) == 1:
        render_data = next(iter(output_data.values()))

    if hint == "markdown": st.markdown(render_data); return
    if hint == "image": st.image(render_data); return
    if hint == "table": st.dataframe(render_data); return

    if is_image_url(render_data): st.image(render_data, caption="Heuristic: Detected Image URL")
    elif is_tabular(render_data): st.dataframe(render_data); st.caption("Heuristic: Detected Tabular Data")
    elif isinstance(render_data, str) and ("\n" in render_data or "#" in render_data or "*" in render_data):
        st.markdown(render_data, help="Heuristic: Detected possible Markdown content")
    else: st.json(output_data, expanded=True)

def run_async(coro):
    loop = asyncio.get_event_loop(); return loop.run_until_complete(coro)

def display_debug_log(workflow_def: dict):
    if not st.session_state.get('debug_records'):
        return
        
    steps_config = {step['name']: step for step in workflow_def.get('steps', [])}
    for record in sorted(st.session_state.debug_records, key=lambda r: r.get('timestamp', 0)):
        step_name, status = record.get('step_name', 'Unknown'), record.get('status', 'Unknown')
        color = "grey"
        if status == "Completed":
            color = "green"
        elif status == "Running":
            color = "orange"
        elif status == "Failed":
            color = "red"
            
        with st.expander(f":{color}[●] **{step_name}** (`{record.get('type')}`) - {record.get('duration_ms', 0):.2f} ms"):
            st.subheader("Data Flow"); colA, colB = st.columns(2)
            colA.markdown("**Inputs**"); colA.json(record.get('inputs', {})); colB.markdown("**Outputs**"); colB.json(record.get('outputs', {}))
            if status == "Failed" and "error" in record:
                st.subheader(":red[Error Details]"); st.error(record["error"].get("message", "No message."))
                with st.expander("Show Traceback"): st.code(record["error"].get("traceback", "No traceback."), language="text")
            st.subheader("Node Config"); st.json(steps_config.get(step_name, {}).get('params', {}))

# --- CORE APP LOGIC ---

st.set_page_config(layout="wide", page_title="AI Workflow Engine")

@st.cache_resource
def initialize_base_resources():
    return ResourceProvider(db_manager=DatabaseManager(settings.mongo_uri))

@st.cache_data
def get_available_workflows(directory: str) -> Dict[str, Path]:
    root_dir = Path(directory); workflows = {}
    if not root_dir.is_dir(): return {}
    for f in sorted(root_dir.glob("*/workflow.yaml")):
        workflows[f.parent.name.replace("_", " ").title()] = f
    return workflows

@st.cache_data
def load_workflow_content(workflow_path: Path) -> (dict, str):
    with open(workflow_path, 'r') as f: content = f.read()
    return yaml.safe_load(content), content

async def execute_workflow(resources: ResourceProvider, workflow_def: WorkflowDefinition, workflow_path: Path, initial_state: dict, dag_placeholder, log_placeholder, sub_dag_area):
    st.session_state.debug_records, st.session_state.sub_dags, st.session_state.step_lifecycle = [], {}, {}
    workflow_dict = workflow_def.model_dump(exclude_none=True)
    full_initial_state = {"workflow_data": initial_state.get("workflow_data", {}), "execution_log": [], "debug_log": [], "error_info": []}
    
    with st.status("Executing workflow...", expanded=True) as status:
        async for event in run_workflow_streaming(resources, workflow_dict, workflow_path, full_initial_state):
            if event["type"] == "lifecycle_update":
                update_data = event["data"]; st.session_state.step_lifecycle[update_data["step_name"]] = update_data["status"]
                dag_placeholder.graphviz_chart(generate_dag_image(workflow_dict, st.session_state.step_lifecycle)); await asyncio.sleep(0.01)
            elif event["type"] == "log":
                record = event["data"]; st.session_state.debug_records.append(record)
                with log_placeholder.container(): display_debug_log(workflow_dict)
                await asyncio.sleep(0.01)
            elif event["type"] == "sub_workflow_event":
                data = event["data"]; parent_step, sub_workflow_name = data["parent_step"], data["sub_workflow"]; original_event = data["original_event"]
                if parent_step not in st.session_state.sub_dags:
                    sub_workflow_yaml_path = workflow_path.parent / sub_workflow_name / "workflow.yaml"
                    sub_workflow_dict, _ = load_workflow_content(sub_workflow_yaml_path)
                    sub_step_names = {step['name'] for step in sub_workflow_dict.get('steps', [])}
                    expander = sub_dag_area.expander(f"Sub-Workflow: `{parent_step}` (`{sub_workflow_name}`)", expanded=True)
                    st.session_state.sub_dags[parent_step] = {"dict": sub_workflow_dict, "lifecycle": {name: StepLifecycle.PENDING.value for name in sub_step_names}, "placeholder": expander.empty()}
                sub_dag_state = st.session_state.sub_dags[parent_step]; event_type = original_event["event"]
                if event_type == "on_chain_start" and original_event["name"] != "__root__": sub_dag_state["lifecycle"][original_event["name"]] = "RUNNING"
                elif event_type == "on_chain_end":
                    node_output = original_event["data"].get("output", {})
                    if "debug_log" in node_output and node_output["debug_log"]:
                        log_data = node_output["debug_log"][0]; sub_dag_state["lifecycle"][log_data["step_name"]] = log_data["status"].upper()
                sub_dag_state["placeholder"].graphviz_chart(generate_dag_image(sub_dag_state["dict"], sub_dag_state["lifecycle"])); await asyncio.sleep(0.01)
            elif event["type"] == "result":
                st.session_state.last_run_state = event["data"]
                if event["data"].get("error_info"): status.update(label="Workflow failed!", state="error")
                else: status.update(label="Workflow complete!", state="complete")

# --- UI LAYOUT ---

st.set_page_config(layout="wide", page_title="AI Workflow Engine")
st.title("Declarative AI Workflow Engine")
resources = initialize_base_resources()

# Initialize session state
st.session_state.setdefault('selected_workflow', None)
st.session_state.setdefault('last_run_state', None)
st.session_state.setdefault('debug_records', [])

# --- Sidebar ---
st.sidebar.title("Workflows")
workflow_dir = "src/workflows"
available_workflows = get_available_workflows(workflow_dir)

if not available_workflows: st.error(f"No workflow packages found in `{workflow_dir}`."); st.stop()

workflow_titles = list(available_workflows.keys())
if st.session_state.selected_workflow is None:
    st.session_state.selected_workflow = workflow_titles[0]

for name in workflow_titles:
    if st.sidebar.button(name, key=f"btn_{name}", use_container_width=True):
        if st.session_state.selected_workflow != name:
            st.session_state.selected_workflow = name
            st.session_state.last_run_state = None
            st.session_state.debug_records = []
            st.rerun()

# --- Main Page ---
selected_workflow_name = st.session_state.selected_workflow
workflow_path = available_workflows[selected_workflow_name]
try:
    workflow_dict, workflow_yaml_content = load_workflow_content(workflow_path)
    workflow_def = WorkflowDefinition.model_validate(workflow_dict)
except (yaml.YAMLError, ValidationError) as e: st.error(f"Invalid YAML for '{selected_workflow_name}': {e}"); st.stop()

col1, col2 = st.columns([1, 2])

with col1:
    st.header(workflow_def.name)
    st.info(f"**Description:** {workflow_def.description}")
    
    with st.form(key="workflow_form"):
        st.subheader("Pipeline Inputs")
        initial_ui_state = {}
        for wf_input in workflow_def.inputs:
            key = f"input_{wf_input.name}"
            if wf_input.type == "text":
                default_val = wf_input.default or ""
                if len(default_val) > 80 or "\n" in default_val:
                    initial_ui_state[wf_input.name] = st.text_area(wf_input.label, value=default_val, height=150, key=key)
                else:
                    initial_ui_state[wf_input.name] = st.text_input(wf_input.label, value=default_val, key=key)
            elif wf_input.type == "json":
                json_string = json.dumps(wf_input.default or {}, indent=2)
                edited_json_str = st.text_area(wf_input.label, value=json_string, height=250, key=key, help="Enter a valid JSON object.")
                try:
                    initial_ui_state[wf_input.name] = json.loads(edited_json_str)
                except json.JSONDecodeError:
                    st.error("Invalid JSON format. Please correct it before running."); initial_ui_state[wf_input.name] = None
            elif wf_input.type == "file":
                initial_ui_state[wf_input.name] = st.file_uploader(wf_input.label, type=["png", "jpg", "jpeg", "pdf"], key=key)

        with st.expander("View Workflow YAML"):
            st.code(workflow_yaml_content, language="yaml")
        
        submitted = st.form_submit_button("Run Pipeline", type="primary", use_container_width=True)

    if submitted:
        run_inputs = {}
        has_error = False
        for wf_input in workflow_def.inputs:
            ui_val = initial_ui_state.get(wf_input.name)
            if ui_val is None and wf_input.type == 'json':
                has_error = True; break
            if wf_input.type == "file":
                if not ui_val: has_error = True; st.error(f"Required file not uploaded: {wf_input.label}"); break
                run_inputs[wf_input.name] = {"data": ui_val.getvalue(), "mime_type": ui_val.type}
            else:
                run_inputs[wf_input.name] = ui_val
        
        if not has_error:
            with col2:
                dag_placeholder = st.empty()
                st.subheader("Live Execution Log"); log_placeholder = st.empty(); sub_dag_area = st.container()
                try:
                    run_async(execute_workflow(resources, workflow_def, workflow_path, {"workflow_data": run_inputs}, dag_placeholder, log_placeholder, sub_dag_area))
                except Exception as e:
                    st.error(f"An unexpected error occurred during execution: {e}"); st.exception(e)

with col2:
    # st.subheader("Execution Plan & Status")
    if not st.session_state.last_run_state and not st.session_state.debug_records:
        st.graphviz_chart(generate_dag_image(workflow_def.model_dump(exclude_none=True)))
        st.info("Live status will appear here after a run is started.")
    # else:
    #     # This ensures the final state of the DAG and logs are shown
    #     dag_placeholder = st.empty()
    #     dag_placeholder.graphviz_chart(generate_dag_image(workflow_dict, st.session_state.get('step_lifecycle', {})))
    #     st.subheader("Execution Log")
    #     log_placeholder = st.empty()
    #     with log_placeholder.container():
    #         display_debug_log(workflow_dict)
    #     sub_dag_area = st.container()

if st.session_state.last_run_state:
    st.divider()
    st.header("Final Workflow Outputs")
    final_state = st.session_state.last_run_state
    workflow_outputs = final_state.get("workflow_data", {})
    output_hints = {out.name: out.display_hint for out in workflow_def.outputs or []}
    if not workflow_outputs:
        st.info("The workflow did not produce any final outputs.")
    else:
        for key, value in workflow_outputs.items():
            render_output(key, value, output_hints); st.markdown("---")
    
    with st.expander("View Full Raw State (JSON)"):
        st.json(final_state)