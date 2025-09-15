import random
from pydantic import BaseModel, Field
from typing import Dict, Any

from src.services.custom_code.base import BaseCustomStep

class EnrichCompanyProfileInput(BaseModel):
    company_name: str

class EnrichCompanyProfileOutput(BaseModel):
    enriched_profile: Dict[str, Any]

class EnrichCompanyProfileStep(BaseCustomStep):
    InputModel = EnrichCompanyProfileInput
    OutputModel = EnrichCompanyProfileOutput

    async def execute(self, input_data: EnrichCompanyProfileInput) -> EnrichCompanyProfileOutput:
        """
        Simulates an external API call to enrich a company profile.
        In a real application, this would query a database or a service like Clearbit.
        """
        print(f"[CUSTOM CODE] Enriching profile for company: '{input_data.company_name}'")
        
        # Simulate fetching data
        industries = ["SaaS", "Manufacturing", "Healthcare", "Fintech"]
        locations = ["New York, NY", "San Francisco, CA", "Austin, TX", "Remote"]
        
        profile_data = {
            "company_name": input_data.company_name,
            "employee_count": random.randint(10, 5000),
            "industry": random.choice(industries),
            "hq_location": random.choice(locations),
            "is_public": random.choice([True, False])
        }
        
        return EnrichCompanyProfileOutput(enriched_profile=profile_data)