import streamlit as st
import asyncio
import yaml
import graphviz

from src.config.settings import settings
from src.data_layer.database_manager import DatabaseManager
from src.llm_integration.gemini_client import GeminiClient
from src.services.pipeline.resource_provider import ResourceProvider
from src.services.pipeline.orchestrator import PipelineOrchestrator
from src.domain.models import TurnContext

st.set_page_config(layout="wide", page_title="Conversational AI Workflow Engine")

@st.cache_resource
def initialize_engine():
    """Initializes all the core components of the workflow engine."""
    print("[INFO] Initializing Workflow Engine Resources...")
    db_manager = DatabaseManager(settings.mongo_uri)
    gemini_client = GeminiClient()
    
    resources = ResourceProvider(
        db_manager=db_manager,
        gemini_client=gemini_client
    )
    
    print("[INFO] Engine Initialized.")
    return resources

def render_dag(workflow_def: dict):
    """Renders the workflow DAG using Graphviz."""
    dot = graphviz.Digraph(comment='Workflow DAG')
    dot.attr('graph', bgcolor='transparent', rankdir='LR')
    dot.attr('node', shape='box', style='rounded,filled', fillcolor='#262730', fontcolor='white', color='#3dd56d')
    dot.attr('edge', color='white', fontcolor='white')

    steps = workflow_def.get('steps', [])
    for step in steps:
        dot.node(step['name'], step['name'])
        for dep in step.get('dependencies', []):
            dot.edge(dep, step['name'])
    
    st.graphviz_chart(dot)

def main():
    st.title("Conversational AI Workflow Engine")
    st.markdown("An interactive tool to build, visualize, and test component-based AI pipelines.")

    resources = initialize_engine()

    # --- Workflow Editor Column ---
    col1, col2 = st.columns([1, 2])
    with col1:
        st.subheader("Workflow Editor")

        if 'workflow_text' not in st.session_state:
            with open("src/services/pipeline/workflows/standard_workflow.yaml", 'r') as f:
                st.session_state.workflow_text = f.read()

        edited_workflow = st.text_area(
            "Modify the workflow YAML and click 'Run Pipeline' to see it in action.",
            value=st.session_state.workflow_text,
            height=400
        )
        st.session_state.workflow_text = edited_workflow
        
        try:
            workflow_def = yaml.safe_load(edited_workflow)
            st.subheader("Execution Plan (DAG)")
            render_dag(workflow_def)
        except yaml.YAMLError as e:
            st.error(f"Invalid YAML syntax: {e}")
            return

    # --- Pipeline Execution Column ---
    with col2:
        st.subheader("Pipeline Execution")
        user_message = st.text_input("Enter User Message:", "I think the new USB-C port is great, but the battery life seems worse.")

        if st.button("Run Pipeline", type="primary"):
            try:
                # Re-initialize orchestrator with the potentially edited workflow
                orchestrator = PipelineOrchestrator(workflow_def, resources)
            except ValueError as e:
                st.error(f"Workflow Configuration Error: {e}")
                return

            with st.spinner("Executing workflow..."):
                initial_context = TurnContext(
                    user_message=user_message,
                    session_id="test_session_123",
                    active_sub_topic_id="sub_123_batterylife"
                )

                try:
                    final_context = asyncio.run(orchestrator.run(initial_context))
                    st.session_state.last_run_context = final_context
                except Exception as e:
                    st.error(f"An error occurred during pipeline execution: {e}")
                    st.exception(e)
                    st.session_state.last_run_context = None

        st.divider()

        if 'last_run_context' in st.session_state and st.session_state.last_run_context:
            final_context = st.session_state.last_run_context
            st.subheader("Pipeline Results")

            tab1, tab2, tab3, tab4 = st.tabs(["Final Context", "Data Flow", "Prompt Inspector", "Debug Log"])

            with tab1:
                st.json(final_context.to_dict())

            with tab2:
                st.markdown("Shows the declared inputs and outputs for each step.")
                for step_name in orchestrator.execution_order:
                    with st.expander(f"Step: **{step_name}**"):
                        st.write("**Inputs Required:**")
                        st.json(final_context.step_inputs.get(step_name, []))
                        st.write("**Outputs Produced:**")
                        st.json(final_context.step_outputs.get(step_name, []))
            
            with tab3:
                st.markdown("Shows the final, fully-constructed prompt sent to the LLM for each relevant step.")
                for step_name, prompt_text in final_context.step_prompts.items():
                    with st.expander(f"Prompt for Step: **{step_name}**"):
                        st.code(prompt_text, language='markdown')

            with tab4:
                st.code("\n".join(final_context.get_debug_log()), language=None)

if __name__ == "__main__":
    main()