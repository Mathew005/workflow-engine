import graphviz
from typing import Dict, Any, Optional

LIFECYCLE_COLORS = {
    "PENDING": "#5b5b5b",    # Grey
    "RUNNING": "#d5a43d",    # Orange/Yellow
    "COMPLETED": "#3dd56d",  # Green (Original Accent)
    "FAILED": "#d53d3d",     # Red
    "DEFAULT": "#262730",   # Original Dark Color
}

def generate_dag_image(workflow_def: Dict[str, Any], step_states: Optional[Dict[str, str]] = None):
    dot = graphviz.Digraph(comment='Workflow DAG')
    dot.attr('graph', bgcolor='transparent', rankdir='LR')
    dot.attr('node', shape='box', style='rounded,filled', fontcolor='white')
    dot.attr('edge', color='white', fontcolor='white')

    steps = workflow_def.get('steps', [])
    if not steps:
        return dot

    dot.node('__start__', 'START', shape='ellipse', style='filled', fillcolor=LIFECYCLE_COLORS["PENDING"])

    output_to_step_map = {
        step['params']['output_key']: step['name']
        for step in steps
        if 'params' in step and step['params'].get('output_key')
    }
    
    output_to_step_map.update({
        output_key: step['name']
        for step in steps if step['type'] == 'workflow'
        for output_key in step['params'].get('output_mapping', {}).values()
    })

    for step in steps:
        step_name = step['name']
        step_type = step['type']
        
        # Determine node color based on its current lifecycle state
        current_state = step_states.get(step_name, "PENDING") if step_states else "DEFAULT"
        border_color = LIFECYCLE_COLORS["COMPLETED"] # Keep accent border
        fill_color = LIFECYCLE_COLORS.get(current_state, LIFECYCLE_COLORS["DEFAULT"])

        if step_type == "workflow":
            workflow_param = step.get('params', {}).get('workflow_name', 'N/A')
            dot.node(
                step_name, 
                f"{step_name}\n(Workflow: {workflow_param})", 
                shape='component',
                style='rounded,filled',
                fillcolor=fill_color,
                color='#8a7ff7' # Distinct border for workflows
            )
        else:
            dot.node(step_name, f"{step_name}\n({step_type})", fillcolor=fill_color, color=border_color)

    for step in steps:
        step_name = step['name']
        dependencies = step.get('dependencies', [])
        
        if not dependencies:
            dot.edge('__start__', step_name)
        else:
            for dep_key in dependencies:
                source_step_name = output_to_step_map.get(dep_key)
                if source_step_name:
                    dot.edge(source_step_name, step_name)
                else:
                    print(f"[DAG Renderer Warning] Could not find source for dependency '{dep_key}' of step '{step_name}'.")
    
    return dot