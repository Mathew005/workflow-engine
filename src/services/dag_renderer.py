import graphviz
from typing import Dict, Any, Optional

LIFECYCLE_COLORS = {
    "PENDING": "#5b5b5b",
    "RUNNING": "#d5a43d",
    "COMPLETED": "#3dd56d",
    "FAILED": "#d53d3d",
    "DEFAULT": "#262730",
}

def generate_dag_image(workflow_def: Dict[str, Any], step_states: Optional[Dict[str, str]] = None):
    dot = graphviz.Digraph(comment='Workflow DAG')
    dot.attr('graph', bgcolor='transparent', rankdir='LR')
    dot.attr('node', style='rounded,filled', fontcolor='white')
    dot.attr('edge', color='white', fontcolor='white')

    steps = workflow_def.get('steps', [])
    if not steps:
        return dot

    dot.node('__start__', 'START', shape='ellipse', style='filled', fillcolor=LIFECYCLE_COLORS["PENDING"])

    output_to_step_map = {
        step['params']['output_key']: step['name']
        for step in steps if step.get('params', {}).get('output_key')
    }
    output_to_step_map.update({
        output_key: step['name']
        for step in steps if step['type'] == 'workflow'
        for output_key in step['params'].get('output_mapping', {}).values()
    })

    # --- RENDER NODES FIRST ---
    for step in steps:
        step_name = step['name']
        step_type = step['type']
        params = step.get('params', {})
        
        current_state = step_states.get(step_name, "PENDING") if step_states else "DEFAULT"
        border_color = LIFECYCLE_COLORS["COMPLETED"]
        fill_color = LIFECYCLE_COLORS.get(current_state, LIFECYCLE_COLORS["DEFAULT"])

        node_label = f"{step_name}\n({step_type})"
        
        # --- NEW: Add mapping icon if applicable ---
        if params.get('map_input'):
            node_label += " 🔁" # Add repeat icon for visual indication of mapping

        if step_type == "workflow":
            workflow_param = params.get('workflow_name', 'N/A')
            dot.node(step_name, f"{step_name}\n(Workflow: {workflow_param})", shape='component', style='rounded,filled', fillcolor=fill_color, color='#8a7ff7')
        
        # --- NEW: Use diamond shape for conditional routers ---
        elif step_type == "conditional_router":
            dot.node(step_name, node_label, shape='diamond', style='rounded,filled', fillcolor=fill_color, color='#f7b92a')
        
        else:
            dot.node(step_name, node_label, shape='box', fillcolor=fill_color, color=border_color)

    # --- RENDER EDGES SECOND ---
    for step in steps:
        step_name = step['name']
        step_type = step['type']
        dependencies = step.get('dependencies', [])
        
        # Edges from START or other dependencies
        if not dependencies:
            dot.edge('__start__', step_name)
        else:
            for dep_key in dependencies:
                source_step_name = output_to_step_map.get(dep_key)
                if source_step_name:
                    dot.edge(source_step_name, step_name)

        # --- NEW: Render outgoing edges for conditional routers ---
        if step_type == 'conditional_router':
            params = step.get('params', {})
            routing_map = params.get('routing_map', {})
            for condition_value, target_step in routing_map.items():
                if target_step in [s['name'] for s in steps] or target_step == "END":
                    # Use the special __end__ node for clarity if routing to END
                    target_node_id = "__end__" if target_step == "END" else target_step
                    dot.edge(step_name, target_node_id, label=f'is "{condition_value}"')

    return dot