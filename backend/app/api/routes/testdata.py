from fastapi import APIRouter, HTTPException

from app.models.schemas import Agent2GenerationRequest, Agent2GenerationResponse
from app.services.testdata_service import build_test_data_contract

router = APIRouter()

@router.post("/agent2/generate-test-data", response_model=Agent2GenerationResponse)
async def generate_test_data(payload: Agent2GenerationRequest):
    """Agent 2 HTTP boundary.

    Accepts Agent 1 machine-readable JSON and returns a contract that groups data by
    positive, negative, boundary, and validation production classes.
    """
    try:
        result = build_test_data_contract(payload)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Agent 2 failed to generate test data: {exc}")

@router.get("/agent2/health")
async def agent2_health():
    return {"service": "agent2-test-data", "status": "ok"}
