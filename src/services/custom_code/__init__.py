from .functions import (
    is_message_long_enough,
    get_user_profile_by_intent,
    fetch_external_data,
)

# This registry is the bridge between your declarative YAML and your Python code.
# The 'function_name' in a 'code' step in your workflow YAML must be a key in this dictionary.
CODE_STEP_REGISTRY = {
    "is_message_long_enough": is_message_long_enough,
    "get_user_profile_by_intent": get_user_profile_by_intent,
    "fetch_external_data": fetch_external_data,
}