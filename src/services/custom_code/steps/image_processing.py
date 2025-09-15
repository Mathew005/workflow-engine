from pydantic import BaseModel, Field
from typing import Dict, Any

from src.services.custom_code.base import BaseCustomStep

class ExtractImageMetadataInput(BaseModel):
    # The engine passes file uploads as a dict with 'data' and 'mime_type'
    image_file: Dict[str, Any]

class ExtractImageMetadataOutput(BaseModel):
    size_kb: float = Field(..., description="The size of the image in kilobytes.")
    mime_type: str = Field(..., description="The MIME type of the image file.")

class ExtractImageMetadataStep(BaseCustomStep):
    """Extracts basic file metadata from an uploaded image."""
    InputModel = ExtractImageMetadataInput
    OutputModel = ExtractImageMetadataOutput

    async def execute(self, input_data: ExtractImageMetadataInput) -> ExtractImageMetadataOutput:
        image_data = input_data.image_file
        
        byte_data = image_data.get("data", b"")
        size_in_kb = len(byte_data) / 1024.0
        
        return ExtractImageMetadataOutput(
            size_kb=round(size_in_kb, 2),
            mime_type=image_data.get("mime_type", "unknown")
        )