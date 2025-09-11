from .llm_executor import LlmExecutor
from .code_executor import CodeExecutor
# To extend the engine, you could add a new executor here, e.g.:
# from .db_query_executor import DbQueryExecutor

# This registry maps the 'type' string from the workflow.yaml file
# to the corresponding generic executor class.
EXECUTOR_REGISTRY = {
    "llm": LlmExecutor,
    "code": CodeExecutor,
    # "db_query": DbQueryExecutor,
}