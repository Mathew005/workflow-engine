import streamlit as st
import asyncio
import yaml
from typing import Dict, Any

from src.config.settings import settings
from src.data_layer.database_manager import DatabaseManager
from src.llm_integration.gemini_client import GeminiClient
from src.services.pipeline.resource_provider import ResourceProvider
from src.services.langgraph_builder import LangGraphBuilder
from src.services.dag_renderer import generate_dag_image
from src.services.graph_streaming import stream_graph_events

st.set_page_config(layout="wide", page_title="LangGraph AI Workflow Engine")

@st.cache_resource
def initialize_engine():
    st.write("[INFO] Initializing Workflow Engine Resources...")
    db_manager = DatabaseManager(settings.mongo_uri)
    gemini_client = GeminiClient()
    resources = ResourceProvider(db_manager=db_manager, gemini_client=gemini_client)
    st.write("[INFO] Engine Initialized.")
    return resources

async def run_pipeline_and_stream_results(graph, initial_state, workflow_def):
    st.subheader("Live Execution Log")
    log_placeholder = st.empty()
    st.session_state.debug_records = []
    
    with st.status("Executing workflow...", expanded=True) as status:
        async for record in stream_graph_events(graph, initial_state):
            st.session_state.debug_records.append(record)
            with log_placeholder.container():
                display_debug_log(st.session_state.debug_records, workflow_def)
        
        status.update(label="Workflow complete!", state="complete")

    final_state = await graph.ainvoke(initial_state)
    st.session_state.last_run_state = final_state

def display_debug_log(debug_records, workflow_def):
    steps_config = {step['name']: step for step in workflow_def.get('steps', [])}
    
    for record in debug_records:
        step_name = record.get('step_name', 'Unknown')
        duration = record.get('duration_ms', 0)
        status = record.get('status', 'Unknown')
        color = "green" if status == "Completed" else "orange"
        
        with st.expander(f":{color}[●] **{step_name}** (`{record.get('type')}`) - {duration:.2f} ms"):
            st.subheader("Data Flow")
            colA, colB = st.columns(2)
            with colA: st.markdown("**Inputs**"); st.json(record.get('inputs', {}))
            with colB: st.markdown("**Outputs**"); st.json(record.get('outputs', {}))
            
            st.subheader("Node Configuration (from YAML)")
            st.json(steps_config.get(step_name, {}).get('params', {}))

def main():
    st.title("Declarative AI Workflow Engine (Powered by LangGraph)")
    resources = initialize_engine()

    col1, col2 = st.columns([1, 2])
    with col1:
        st.subheader("Workflow Editor")
        if 'workflow_text' not in st.session_state:
            with open("src/services/pipeline/workflows/standard_workflow.yaml", 'r') as f: st.session_state.workflow_text = f.read()
        edited_workflow = st.text_area("Modify YAML...", value=st.session_state.workflow_text, height=600)
        st.session_state.workflow_text = edited_workflow
        try:
            workflow_def = yaml.safe_load(edited_workflow)
            st.subheader("Execution Plan (DAG)")
            st.graphviz_chart(generate_dag_image(workflow_def))
        except (yaml.YAMLError, KeyError) as e: st.error(f"Invalid YAML: {e}"); return

    with col2:
        st.subheader("Pipeline Execution")
        user_message = st.text_input("Enter User Message:", "The battery life seems worse.")

        if st.button("Run Pipeline", type="primary"):
            try:
                graph = LangGraphBuilder(workflow_def, resources).build()
            except Exception as e: st.error(f"Workflow Compilation Error: {e}"); st.exception(e); return
            
            initial_state = {"user_message": user_message, "session_id": "test_session_123", "execution_log": []}
            asyncio.run(run_pipeline_and_stream_results(graph, initial_state, workflow_def))

        st.divider()

        if 'last_run_state' in st.session_state and st.session_state.last_run_state:
            st.subheader("Pipeline Results")
            final_state = st.session_state.last_run_state
            
            tab1, tab2 = st.tabs(["Final State", "Execution Summary"])
            with tab1:
                display_state = {k: v for k, v in final_state.items() if k not in ['__end__', 'debug_record']}
                st.json(display_state)
            with tab2:
                st.code("\n".join(final_state.get("execution_log", [])), language=None)

if __name__ == "__main__":
    main()