from pydantic import BaseModel, Field
from typing import List, Dict, Any

from src.custom_code.base import BaseCustomStep

class AddStatusToUsersInput(BaseModel):
    user_list: List[Dict[str, Any]]

class AddStatusToUsersOutput(BaseModel):
    processed_list: List[Dict[str, Any]]

class AddStatusToUsersStep(BaseCustomStep):
    """A simple step that iterates through a list of users and adds a status field."""
    InputModel = AddStatusToUsersInput
    OutputModel = AddStatusToUsersOutput

    async def execute(self, input_data: AddStatusToUsersInput) -> AddStatusToUsersOutput:
        processed = []
        for user in input_data.user_list:
            user['status'] = 'processed'
            processed.append(user)
        
        # The output model requires the data to be under the 'processed_list' key.
        # But the step's output_key in the YAML ('processed_users') will store the
        # entire dictionary {'processed_list': [...]}.
        # For adaptive rendering, we'll want to access the list directly.
        # A more advanced step could just return the list and have a different OutputModel.
        return AddStatusToUsersOutput(processed_list=processed)