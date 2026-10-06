from typing import Any, Dict, List

from agents.agent2.services.testdata_service import TestDataAgentService
from app.models.schemas import Agent2GenerationRequest, Agent2GenerationResponse


def build_test_data_contract(request: Agent2GenerationRequest) -> Agent2GenerationResponse:
    service = TestDataAgentService()
    return service.build_json_response(request)
