import yaml
import asyncio
from typing import Dict, List
from collections import deque

from src.services.pipeline.steps import ALL_STEPS
from src.domain.models import TurnContext
from src.services.pipeline.resource_provider import ResourceProvider
from src.services.pipeline.steps.base_step import PipelineStep

class PipelineOrchestrator:
    """
    Reads a workflow definition, builds an execution graph (DAG),
    and runs the defined pipeline of steps asynchronously, handling parallelism.
    """
    def __init__(self, workflow_definition: dict, resources: ResourceProvider):
        self.workflow_definition = workflow_definition
        self.resources = resources
        
        self.steps: Dict[str, PipelineStep] = {
            s['name']: ALL_STEPS[s['name']] for s in self.workflow_definition['steps']
            if s['name'] in ALL_STEPS
        }
        self.dependencies = {step['name']: step.get('dependencies', []) for step in self.workflow_definition['steps']}
        self.dag = self._build_dag()
        self.execution_order = self._topological_sort()

    def get_workflow_definition_text(self) -> str:
        return yaml.dump(self.workflow_definition)

    def _build_dag(self):
        dag = {name: [] for name in self.steps}
        for step_name, deps in self.dependencies.items():
            for dep in deps:
                if dep in dag:
                    dag[dep].append(step_name)
                else:
                    raise ValueError(f"Workflow Error: Step '{step_name}' has an unknown dependency '{dep}'")
        return dag

    def _topological_sort(self) -> List[str]:
        in_degree = {u: 0 for u in self.dag}
        for u in self.dag:
            for v in self.dag[u]:
                in_degree[v] += 1

        queue = deque([u for u in self.dag if in_degree[u] == 0])
        sorted_order = []

        while queue:
            u = queue.popleft()
            sorted_order.append(u)
            for v in self.dag[u]:
                in_degree[v] -= 1
                if in_degree[v] == 0:
                    queue.append(v)

        if len(sorted_order) != len(self.dag):
            raise ValueError("Workflow Error: A cycle was detected in the workflow dependencies. Execution is impossible.")
        return sorted_order

    async def run(self, initial_context: TurnContext) -> TurnContext:
        context = initial_context
        completed_steps = set()
        steps_to_run = self.execution_order[:]
        
        while steps_to_run:
            batch_to_run_names = []
            
            remaining_after_batch = []
            for step_name in steps_to_run:
                deps = self.dependencies.get(step_name, [])
                if all(dep in completed_steps for dep in deps):
                    batch_to_run_names.append(step_name)
                else:
                    remaining_after_batch.append(step_name)
            
            if not batch_to_run_names:
                raise RuntimeError(f"Workflow Error: Could not resolve dependencies for remaining steps: {remaining_after_batch}")

            # Register IO for all steps in the batch before execution
            for name in batch_to_run_names:
                step = self.steps[name]
                context.set_step_io(name, step.get_required_inputs(), step.get_outputs())

            tasks = [self.steps[name].execute(context, self.resources) for name in batch_to_run_names]
            if tasks:
                context.log(f"--- EXECUTING BATCH: {', '.join(batch_to_run_names)} ---")
                await asyncio.gather(*tasks)
            
            for name in batch_to_run_names:
                completed_steps.add(name)
            steps_to_run = remaining_after_batch
            
        context.log("--- WORKFLOW COMPLETE ---")
        return context