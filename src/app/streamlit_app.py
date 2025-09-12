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

st.set_page_config(layout="wide", page_title="LangGraph AI Workflow Engine")

@st.cache_resource
def initialize_engine():
    st.write("[INFO] Initializing Workflow Engine Resources...")
    db_manager = DatabaseManager(settings.mongo_uri)
    gemini_client = GeminiClient()
    resources = ResourceProvider(db_manager=db_manager, gemini_client=gemini_client)
    st.write("[INFO] Engine Initialized.")
    return resources

def main():
    st.title("Declarative AI Workflow Engine (Powered by LangGraph)")
    st.markdown("An interactive tool to build, visualize, and test configuration-driven AI pipelines.")

    resources = initialize_engine()

    col1, col2 = st.columns([1, 2])
    with col1:
        st.subheader("Workflow Editor")
        if 'workflow_text' not in st.session_state:
            with open("src/services/pipeline/workflows/standard_workflow.yaml", 'r') as f:
                st.session_state.workflow_text = f.read()

        edited_workflow = st.text_area(
            "Modify the workflow YAML...",
            value=st.session_state.workflow_text,
            height=600
        )
        st.session_state.workflow_text = edited_workflow
        
        try:
            workflow_def = yaml.safe_load(edited_workflow)
            st.subheader("Execution Plan (DAG)")
            dag_dot = generate_dag_image(workflow_def)
            st.graphviz_chart(dag_dot)
        except (yaml.YAMLError, KeyError) as e:
            st.error(f"Invalid YAML syntax or structure: {e}")
            return

    with col2:
        st.subheader("Pipeline Execution")
        user_message = st.text_input("Enter User Message:", "The new USB-C port is great, but the battery life seems worse.")

        if st.button("Run Pipeline", type="primary"):
            try:
                builder = LangGraphBuilder(workflow_def, resources)
                graph = builder.build()
            except Exception as e:
                st.error(f"Workflow Compilation Error: {e}")
                st.exception(e)
                return

            with st.spinner("Executing graph..."):
                # The initial state must now include an empty list for our new debug log
                initial_state = {
                    "user_message": user_message,
                    "session_id": "test_session_123",
                    "execution_log": ["--- WORKFLOW START ---"],
                    "debug_log": []
                }
                
                try:
                    final_state = asyncio.run(graph.ainvoke(initial_state))
                    st.session_state.last_run_state = final_state
                except Exception as e:
                    st.error(f"An error occurred during graph execution: {e}")
                    st.exception(e)
                    st.session_state.last_run_state = None

        st.divider()

        if 'last_run_state' in st.session_state and st.session_state.last_run_state:
            final_state = st.session_state.last_run_state
            st.subheader("Pipeline Results")
            
            # --- NEW UI WITH VERBOSE DEBUG TAB ---
            tab1, tab2, tab3 = st.tabs(["Final State", "Execution Summary", "Verbose Debug Log"])

            with tab1:
                # Create a copy to display, removing the verbose log for clarity
                display_state = final_state.copy()
                display_state.pop('debug_log', None)
                display_state.pop('__end__', None)
                st.json(display_state)
            
            with tab2:
                log = final_state.get("execution_log", [])
                st.code("\n".join(log), language=None)

            with tab3:
                st.markdown("A detailed, step-by-step log of the graph execution.")
                debug_log = final_state.get("debug_log", [])
                
                if not debug_log:
                    st.warning("No detailed debug information was recorded.")
                else:
                    # Find the corresponding step configuration from the YAML
                    steps_config = {step['name']: step for step in workflow_def.get('steps', [])}

                    for record in debug_log:
                        step_name = record.get('step_name', 'Unknown Step')
                        duration = record.get('duration_ms', 0)
                        step_type = record.get('type', 'unknown')

                        with st.expander(f"**{step_name}** (`{step_type}`) - Ran in **{duration:.2f} ms**"):
                            
                            st.subheader("Data Flow")
                            colA, colB = st.columns(2)
                            with colA:
                                st.markdown("**Inputs**")
                                st.json(record.get('inputs', {}))
                            with colB:
                                st.markdown("**Outputs**")
                                st.json(record.get('outputs', {}))
                            
                            st.subheader("Node Configuration (from YAML)")
                            config = steps_config.get(step_name, {})
                            st.json(config.get('params', {'Note': 'No parameters defined in YAML.'}))

if __name__ == "__main__":
    main()