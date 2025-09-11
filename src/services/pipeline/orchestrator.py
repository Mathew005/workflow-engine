import yaml
import asyncio
from typing import Dict, List, Any
from collections import deque

from src.services.pipeline.executors import EXECUTOR_REGISTRY
from src.domain.models import TurnContext
from src.services.pipeline.resource_provider import ResourceProvider

class PipelineOrchestrator:
    """
    Reads a workflow definition, builds an execution graph (DAG),
    and runs the defined pipeline of steps asynchronously using generic executors.
    """
    def __init__(self, workflow_definition: dict, resources: ResourceProvider):
        self.workflow_definition = workflow_definition
        self.resources = resources
        
        self.step_configs: Dict[str, Dict[str, Any]] = {s['name']: s for s in self.workflow_definition['steps']}
        self.executors = self._initialize_executors()
        
        self.dependencies: Dict[str, List[str]] = {s['name']: s.get('dependencies', []) for s in self.workflow_definition['steps']}
        
        self.dag, self.step_names = self._build_dag()
        self.execution_order = self._topological_sort()

    def _initialize_executors(self):
        executors = {}
        for step_config in self.workflow_definition.get('steps', []):
            step_name = step_config['name']
            step_type = step_config.get('type')
            if not step_type:
                raise ValueError(f"Workflow Error: Step '{step_name}' is missing a 'type'.")
            
            executor_class = EXECUTOR_REGISTRY.get(step_type)
            if not executor_class:
                raise ValueError(f"Workflow Error: Unknown step type '{step_type}' for step '{step_name}'.")
            
            executors[step_name] = executor_class(step_name, step_config.get('params', {}))
        return executors

    def _build_dag(self):
        step_names = set(self.step_configs.keys())
        dag = {name: [] for name in step_names}

        # --- FIX START: More robust dependency mapping ---
        output_to_step_map = {}
        for s_name, s_config in self.step_configs.items():
            # Check if a step even has an output_key before trying to map it
            if 'params' in s_config and 'output_key' in s_config['params']:
                output_key = s_config['params']['output_key']
                output_to_step_map[output_key] = s_name

        for step_name, deps in self.dependencies.items():
            for dep_key in deps:
                source_step_name = None
                if '.' in dep_key:
                    # Handles granular dependencies like "initial_analysis_result.user_intent"
                    base_output_name = dep_key.split('.')[0]
                    source_step_name = output_to_step_map.get(base_output_name)
                else:
                    # Handles direct output dependencies like "validation_result"
                    source_step_name = output_to_step_map.get(dep_key)

                if not source_step_name or source_step_name not in step_names:
                    raise ValueError(f"Workflow Error: Step '{step_name}' has an unresolved dependency on output '{dep_key}'. Could not find the step that produces this output.")
                
                if step_name not in dag.get(source_step_name, []):
                    dag[source_step_name].append(step_name)
        # --- FIX END ---
        return dag, step_names

    def _topological_sort(self) -> List[str]:
        in_degree = {u: 0 for u in self.step_names}
        for u in self.dag:
            for v in self.dag[u]:
                in_degree[v] += 1

        queue = deque([u for u in self.step_names if in_degree[u] == 0])
        sorted_order = []

        while queue:
            u = queue.popleft()
            sorted_order.append(u)
            for v in self.dag[u]:
                in_degree[v] -= 1
                if in_degree[v] == 0:
                    queue.append(v)

        if len(sorted_order) != len(self.step_names):
            raise ValueError("Workflow Error: A cycle was detected in the workflow dependencies. Execution is impossible.")
        return sorted_order

    async def run(self, initial_context: TurnContext) -> TurnContext:
        context = initial_context
        available_context_keys = set(context.to_dict().keys())
        
        steps_to_run = self.execution_order[:]
        completed_steps = set()

        while steps_to_run:
            batch_to_run_names = []
            
            remaining_after_batch = []
            for step_name in steps_to_run:
                deps = self.dependencies.get(step_name, [])
                if all(dep_key.replace('.', '_') in available_context_keys for dep_key in deps):
                    batch_to_run_names.append(step_name)
                else:
                    remaining_after_batch.append(step_name)

            if not batch_to_run_names and remaining_after_batch:
                missing_deps = {s: [d for d in self.dependencies.get(s, []) if d.replace('.', '_') not in available_context_keys] for s in remaining_after_batch}
                raise RuntimeError(f"Workflow Error: Deadlock detected. Could not resolve dependencies. Missing context keys: {missing_deps}")

            tasks = [self.executors[name].execute(context, self.resources) for name in batch_to_run_names]
            
            if tasks:
                context.log(f"--- EXECUTING BATCH: {', '.join(batch_to_run_names)} ---")
                await asyncio.gather(*tasks)
            
            available_context_keys.update(context.to_dict().keys())

            for name in batch_to_run_names:
                completed_steps.add(name)
            
            steps_to_run = remaining_after_batch
            
        context.log("--- WORKFLOW COMPLETE ---")
        return context