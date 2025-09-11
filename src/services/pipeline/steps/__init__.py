from .parallel_analysis_step import ParallelAnalysisStep
from .data_validation_step import DataValidationStep
from .memory_fetcher_step import MemoryFetcherStep
from .fact_summarizer_step import FactSummarizerStep
from .strategist_step import StrategistStep

# This registry is a central place to map step names (from YAML) to their class instances.
# When you create a new step, you must import it and add it to this dictionary.
ALL_STEPS = {
    "parallel_analysis": ParallelAnalysisStep(),
    "data_validation": DataValidationStep(),
    "memory_fetcher": MemoryFetcherStep(),
    "fact_summarizer": FactSummarizerStep(),
    "strategist": StrategistStep(),
}