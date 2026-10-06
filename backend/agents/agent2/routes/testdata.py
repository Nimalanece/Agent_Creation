from fastapi import APIRouter, HTTPException

from ..models.schemas import Agent2GenerationRequest, Agent2GenerationResponse
from ..services.testdata_service import build_test_data_contract

router = APIRouter()


@router.post("/agent2/generate-test-data", response_model=Agent2GenerationResponse)
async def generate_test_data(payload: Agent2GenerationRequest):
    """HTTP boundary for Agent 2.

    Accepts Agent 1 JSON messages and synthesizes the Agent 2 output contract.
    """
    try:
        return build_test_data_contract(payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Agent 2 failed to generate test data: {exc}")


@router.get("/agent2/health")
async def agent2_health():
    return {"service": "agent2-test-data", "status": "ok"}
