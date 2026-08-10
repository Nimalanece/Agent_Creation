from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.testdata_service import generate_testdata
from app.core.groq_service import GroqServiceError

router = APIRouter()


class TestCasesPayload(BaseModel):
    testcases: Any
    analysis: Optional[Any] = None


@router.post("/testdata", response_model=Dict[str, Any])
async def testdata_endpoint(payload: TestCasesPayload):
    """Generate realistic test data for generated test cases using Groq AI.

    Input: { "testcases": [ ... ] }
    Output: JSON object with test data key/value pairs.
    """
    try:
        parsed = await generate_testdata(payload.testcases, analysis=payload.analysis)
    except GroqServiceError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error generating test data")

    if isinstance(parsed, dict):
        return parsed

    raise HTTPException(status_code=502, detail="Unexpected model output for test data")
