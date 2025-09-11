import streamlit as st
import asyncio
import yaml
import graphviz
import re

from src.config.settings import settings
from src.data_layer.database_manager import DatabaseManager
from src.llm_integration.gemini_client import GeminiClient
from src.services.pipeline.resource_provider import ResourceProvider
from src.services.pipeline.orchestrator import PipelineOrchestrator
from src.domain.models import TurnContext

st.set_page_config(layout="wide", page_title="Declarative AI Workflow Engine")

@st.cache_resource
def initialize_engine():
    """Initializes all the core components of the workflow engine."""
    st.write("[INFO] Initializing Workflow Engine Resources...")
    db_manager = DatabaseManager(settings.mongo_uri)
    gemini_client = GeminiClient()
    
    resources = ResourceProvider(
        db_manager=db_manager,
        gemini_client=gemini_client
    )
    
    st.write("[INFO] Engine Initialized.")
    return resources

def render_dag(workflow_def: dict):
    """Renders the workflow DAG using Graphviz."""
    dot = graphviz.Digraph(comment='Workflow DAG')
    dot.attr('graph', bgcolor='transparent', rankdir='LR')
    dot.attr('node', shape='box', style='rounded,filled', fillcolor='#262730', fontcolor='white', color='#3dd56d')
    dot.attr('edge', color='white', fontcolor='white')

    steps = workflow_def.get('steps', [])
    if not steps:
        return

    # --- FIX START: Create a map to find which step produces which output ---
    output_to_step_map = {}
    for step in steps:
        step_name = step['name']
        # Add a check to prevent KeyErrors if a step has no params or output_key
        if 'params' in step and 'output_key' in step['params']:
            output_key = step['params']['output_key']
            output_to_step_map[output_key] = step_name
    # --- FIX END ---

    for step in steps:
        step_name = step['name']
        dot.node(step_name, f"{step_name}\n({step['type']})")
        
        for dep_key in step.get('dependencies', []):
            source_step_name = None
            # Find the source step using the same logic as the orchestrator
            if '.' in dep_key:
                base_output = dep_key.split('.')[0]
                source_step_name = output_to_step_map.get(base_output)
            else:
                source_step_name = output_to_step_map.get(dep_key)
            
            if source_step_name:
                dot.edge(source_step_name, step_name)
    
    st.graphviz_chart(dot)


def main():
    st.title("Declarative Conversational AI Workflow Engine")
    st.markdown("An interactive tool to build, visualize, and test configuration-driven AI pipelines.")

    resources = initialize_engine()

    col1, col2 = st.columns([1, 2])
    with col1:
        st.subheader("Workflow Editor")

        if 'workflow_text' not in st.session_state:
            with open("src/services/pipeline/workflows/standard_workflow.yaml", 'r') as f:
                st.session_state.workflow_text = f.read()

        edited_workflow = st.text_area(
            "Modify the workflow YAML and click 'Run Pipeline' to see it in action.",
            value=st.session_state.workflow_text,
            height=600,
            key="yaml_editor"
        )
        st.session_state.workflow_text = edited_workflow
        
        try:
            workflow_def = yaml.safe_load(edited_workflow)
            st.subheader("Execution Plan (DAG)")
            render_dag(workflow_def)
        except yaml.YAMLError as e:
            st.error(f"Invalid YAML syntax: {e}")
            return

    with col2:
        st.subheader("Pipeline Execution")
        user_message = st.text_input("Enter User Message:", "I think the new USB-C port is great, but the battery life seems worse.")

        if st.button("Run Pipeline", type="primary"):
            try:
                # The orchestrator is now created here, which is fine.
                orchestrator = PipelineOrchestrator(workflow_def, resources)
            except Exception as e:
                st.error(f"Workflow Configuration Error: {e}")
                st.exception(e)
                return

            with st.spinner("Executing workflow..."):
                initial_context = TurnContext(
                    user_message=user_message,
                    session_id="test_session_123"
                )

                try:
                    final_context = asyncio.run(orchestrator.run(initial_context))
                    st.session_state.last_run_context = final_context
                    # Store the successful orchestrator instance to reuse its properties for display
                    st.session_state.last_orchestrator = orchestrator 
                except Exception as e:
                    st.error(f"An error occurred during pipeline execution: {e}")
                    st.exception(e)
                    st.session_state.last_run_context = None

        st.divider()

        if 'last_run_context' in st.session_state and st.session_state.last_run_context:
            final_context = st.session_state.last_run_context
            orchestrator = st.session_state.last_orchestrator
            st.subheader("Pipeline Results")

            tab1, tab2, tab3, tab4 = st.tabs(["Final Context", "Data Flow", "Prompt Inspector", "Debug Log"])

            with tab1:
                st.json(final_context.to_dict())

            with tab2:
                st.markdown("Shows the declared inputs and outputs for each step as defined in the YAML.")
                for step_name in orchestrator.execution_order:
                    with st.expander(f"Step: **{step_name}**"):
                        st.write("**Inputs (from Context):**")
                        st.json(final_context.step_inputs.get(step_name, {}))
                        st.write("**Outputs (to Context):**")
                        st.json(final_context.step_outputs.get(step_name, []))

            with tab3:
                st.markdown("Shows the final, fully-constructed prompt sent to the LLM for each `llm` step.")
                if not final_context.step_prompts:
                    st.info("No LLM steps were executed or no prompts were recorded.")
                for step_name, prompt_text in final_context.step_prompts.items():
                    with st.expander(f"Prompt for Step: **{step_name}**"):
                        st.code(prompt_text, language='markdown')

            with tab4:
                st.code("\n".join(final_context.get_debug_log()), language=None)

if __name__ == "__main__":
    main()