import graphviz
from typing import Dict, Any

def generate_dag_image(workflow_def: Dict[str, Any]):
    """
    Generates a Graphviz Digraph object from a workflow definition.
    This centralized logic ensures the visualization perfectly matches execution.
    """
    dot = graphviz.Digraph(comment='Workflow DAG')
    dot.attr('graph', bgcolor='transparent', rankdir='LR')
    dot.attr('node', shape='box', style='rounded,filled', fillcolor='#262730', fontcolor='white', color='#3dd56d')
    dot.attr('edge', color='white', fontcolor='white')

    steps = workflow_def.get('steps', [])
    if not steps:
        return dot

    # Add the START node for clarity
    dot.node('__start__', 'START', shape='ellipse', style='filled', fillcolor='#5b5b5b')

    # Create the mapping of which step produces which output.
    # This logic is now guaranteed to be correct and centralized.
    output_to_step_map = {
        step['params']['output_key']: step['name']
        for step in steps
        if 'params' in step and 'output_key' in step.get('params', {})
    }

    # 1. Add all nodes to the graph first
    for step in steps:
        step_name = step['name']
        step_type = step['type']
        dot.node(step_name, f"{step_name}\n({step_type})")

    # 2. Add all edges by iterating again
    for step in steps:
        step_name = step['name']
        dependencies = step.get('dependencies', [])
        
        if not dependencies:
            # Connect steps with no dependencies to the START node
            dot.edge('__start__', step_name)
        else:
            for dep_key in dependencies:
                # Find the source step by looking up the dependency key in our map
                source_step_name = output_to_step_map.get(dep_key)
                
                if source_step_name:
                    dot.edge(source_step_name, step_name)
                else:
                    # This provides a clear error if the YAML is misconfigured
                    print(f"[DAG Renderer Warning] Could not find source for dependency '{dep_key}' of step '{step_name}'. Edge will not be drawn.")
    
    return dot