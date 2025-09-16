from pathlib import Path
from typing import Dict, Any

from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import Runnable

from .pipeline.resource_provider import ResourceProvider
from .node_factory import create_node_function
from .graph_types import GraphState, _resolve_value_from_state

# This is now only used for sub-workflow compilation, keeping it scoped here.
COMPILED_WORKFLOW_CACHE: Dict[str, Runnable] = {}

class LangGraphBuilder:
    def __init__(self, workflow_definition: dict, resources: ResourceProvider, workflow_path: Path):
        self.workflow_def = workflow_definition
        self.resources = resources
        self.workflow_package_path = workflow_path.parent 
        self.graph_builder = StateGraph(GraphState)
        self.output_to_step_map = self._build_output_map()
        self.steps_by_name = {step['name']: step for step in self.workflow_def.get('steps', [])}

    def _build_output_map(self) -> Dict[str, str]:
        """Creates a mapping from an output key to the name of the step that produces it."""
        output_map = {}
        for step in self.workflow_def.get('steps', []):
            params = step.get('params', {})
            if params.get('output_key'): output_map[params['output_key']] = step['name']
            if step['type'] == 'workflow' and params.get('output_mapping'):
                for out_key in params['output_mapping'].values(): output_map[out_key] = step['name']
        return output_map

    def build(self) -> Runnable:
        """
        Constructs the LangGraph graph from the workflow definition, now with corrected
        logic for handling all dependency types, especially fan-in joins.
        """
        steps = self.workflow_def.get('steps', [])
        
        # 1. Add all nodes to the graph first.
        for step in steps:
            step_name, step_type, step_params = step['name'], step['type'], step.get('params', {})
            if step_type == 'conditional_router':
                self.graph_builder.add_node(step_name, lambda state: state)
            else:
                node_function = create_node_function(self.resources, self.workflow_package_path, step_name, step_type, step_params)
                self.graph_builder.add_node(step_name, node_function)

        # 2. Identify all nodes that are targets of a router to prevent incorrect START connections.
        router_targets = {target for s in steps if s['type'] == 'conditional_router' for target in s.get('params', {}).get('routing_map', {}).values()}
        
        # 3. Add all edges to the graph.
        for step in steps:
            step_name = step['name']
            step_type = step['type']
            dependencies = step.get('dependencies', [])
            
            if step_type == 'conditional_router':
                source_nodes = {self.output_to_step_map[dep] for dep in dependencies if dep in self.output_to_step_map}
                if not source_nodes: raise ValueError(f"Router step '{step_name}' must have dependencies.")
                # Routers are simple: they depend on their parents finishing, so we connect them directly.
                self.graph_builder.add_edge(list(source_nodes), step_name)
                
                params = step.get('params', {})
                condition_key = params['condition_key']
                routing_map = params['routing_map']

                def create_conditional_func(key: str):
                    def conditional_func(state: GraphState):
                        value = _resolve_value_from_state(state.get("workflow_data", {}), key)
                        return str(value)
                    return conditional_func
                
                self.graph_builder.add_conditional_edges(step_name, create_conditional_func(condition_key), routing_map)

            else:
                # --- THIS IS THE DEFINITIVE FIX FOR THE RACE CONDITION ---
                source_nodes = {self.output_to_step_map[dep] for dep in dependencies if dep in self.output_to_step_map}

                if not source_nodes:
                    # No dependencies: connect from START if it's not a router target
                    if step_name not in router_targets:
                        self.graph_builder.add_edge(START, step_name)
                else:
                    # One or more dependencies: connect from a list of all parents.
                    # LangGraph handles both single-item lists and multi-item lists correctly,
                    # ensuring it waits for ALL of them before executing the step.
                    self.graph_builder.add_edge(list(source_nodes), step_name)

        # 4. Connect terminal nodes to the END node.
        all_step_names = {s['name'] for s in steps}
        # A step is a dependency source if another step depends on its output.
        dependency_sources = {self.output_to_step_map[dep] for s in steps for dep in s.get('dependencies', []) if dep in self.output_to_step_map}
        # Routers are also dependency sources.
        for step in steps:
            if step['type'] == 'conditional_router':
                dependency_sources.add(step['name'])
        
        terminal_nodes = all_step_names - dependency_sources
        for node in terminal_nodes:
            # A router itself cannot be a terminal node. Its paths lead to other nodes or END.
            if self.steps_by_name[node]['type'] != 'conditional_router':
                self.graph_builder.add_edge(node, END)
        
        return self.graph_builder.compile()