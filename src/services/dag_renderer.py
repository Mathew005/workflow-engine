import graphviz
from typing import Dict, Any, Optional

LIFECYCLE_COLORS = {
    "PENDING": "#5b5b5b", "RUNNING": "#d5a43d",
    "COMPLETED": "#3dd56d", "FAILED": "#d53d3d", "DEFAULT": "#262730",
}

def generate_dag_image(workflow_def: Dict[str, Any], step_states: Optional[Dict[str, str]] = None):
    dot = graphviz.Digraph(comment='Workflow DAG')
    dot.attr('graph', bgcolor='transparent', rankdir='LR')
    dot.attr('node', style='rounded,filled', fontcolor='white')
    dot.attr('edge', color='white', fontcolor='white')

    steps = workflow_def.get('steps', [])
    if not steps: return dot

    dot.node('__start__', 'START', shape='ellipse', style='filled', fillcolor=LIFECYCLE_COLORS["PENDING"])

    output_to_step_map = {
        step['params']['output_key']: step['name']
        for step in steps if step.get('params', {}).get('output_key')
    }
    output_to_step_map.update({
        out_key: step['name'] for step in steps if step['type'] == 'workflow'
        for out_key in step['params'].get('output_mapping', {}).values()
    })

    router_targets = {target for s in steps if s['type'] == 'conditional_router' for target in s.get('params', {}).get('routing_map', {}).values()}

    for step in steps:
        step_name, step_type, params = step['name'], step['type'], step.get('params', {})
        current_state = step_states.get(step_name, "PENDING") if step_states else "DEFAULT"
        border_color = LIFECYCLE_COLORS["COMPLETED"]
        fill_color = LIFECYCLE_COLORS.get(current_state, LIFECYCLE_COLORS["DEFAULT"])
        node_label = f"{step_name}\n({step_type})"
        if params.get('map_input'): node_label += " 🔁"
        if step_type == "workflow":
            dot.node(step_name, f"{step_name}\n(Workflow: {params.get('workflow_name', 'N/A')})", shape='component', style='rounded,filled', fillcolor=fill_color, color='#8a7ff7')
        elif step_type == "conditional_router":
            dot.node(step_name, node_label, shape='diamond', style='rounded,filled', fillcolor=fill_color, color='#f7b92a')
        else:
            dot.node(step_name, node_label, shape='box', fillcolor=fill_color, color=border_color)

    for step in steps:
        step_name, step_type, dependencies = step['name'], step['type'], step.get('dependencies', [])
        
        if not dependencies and step_name not in router_targets:
            dot.edge('__start__', step_name)
        else:
            for dep_key in dependencies:
                source_step_name = output_to_step_map.get(dep_key)
                if source_step_name:
                    source_step_params = next((s['params'] for s in steps if s['name'] == source_step_name), {})
                    edge_label = "[list]" if source_step_params.get('map_input') == dep_key else ""
                    dot.edge(source_step_name, step_name, label=edge_label)

        if step_type == 'conditional_router':
            routing_map = step.get('params', {}).get('routing_map', {})
            for condition_value, target_step in routing_map.items():
                target_node_id = "__end__" if target_step == "END" else target_step
                dot.edge(step_name, target_node_id, label=f'is "{condition_value}"')

    return dot