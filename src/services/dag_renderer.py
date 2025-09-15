import graphviz
from typing import Dict, Any

def generate_dag_image(workflow_def: Dict[str, Any]):
    dot = graphviz.Digraph(comment='Workflow DAG')
    dot.attr('graph', bgcolor='transparent', rankdir='LR')
    dot.attr('node', shape='box', style='rounded,filled', fillcolor='#262730', fontcolor='white', color='#3dd56d')
    dot.attr('edge', color='white', fontcolor='white')

    steps = workflow_def.get('steps', [])
    if not steps:
        return dot

    dot.node('__start__', 'START', shape='ellipse', style='filled', fillcolor='#5b5b5b')

    output_to_step_map = {
        step['params']['output_key']: step['name']
        for step in steps
        if 'params' in step and step['params'].get('output_key')
    }
    
    # Add nodes mapped from output_mapping for workflows
    output_to_step_map.update({
        output_key: step['name']
        for step in steps if step['type'] == 'workflow'
        for output_key in step['params'].get('output_mapping', {}).values()
    })

    for step in steps:
        step_name = step['name']
        step_type = step['type']
        
        # --- NEW VISUAL LOGIC ---
        if step_type == "workflow":
            workflow_param = step.get('params', {}).get('workflow_name', 'N/A')
            dot.node(
                step_name, 
                f"{step_name}\n(Workflow: {workflow_param})", 
                shape='component',
                style='rounded,filled',
                fillcolor='#4b3dd5'
            )
        else:
            dot.node(step_name, f"{step_name}\n({step_type})")

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