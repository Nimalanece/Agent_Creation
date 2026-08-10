from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.testcases_service import generate_testcases
from app.models.groq_models import TestCaseList
from app.core.groq_service import GroqServiceError

router = APIRouter()


class ScenariosPayload(BaseModel):
    scenarios: Any


@router.post("/testcases", response_model=TestCaseList)
async def testcases_endpoint(payload: ScenariosPayload):
    """Generate detailed test cases from provided scenarios using Groq AI.

    Input: { "scenarios": [ ... ] }
    Output: { "testcases": [ ... ] }
    """
    try:
        parsed = await generate_testcases(payload.scenarios)
    except GroqServiceError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error generating testcases")

    if isinstance(parsed, dict) and "testcases" in parsed:
        return parsed
    if isinstance(parsed, list):
        return {"testcases": parsed}

    raise HTTPException(status_code=502, detail="Unexpected model output for testcases")
