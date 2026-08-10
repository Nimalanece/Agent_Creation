from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models.groq_models import ScenarioList
from app.services.scenarios_service import generate_scenarios
from app.core.groq_service import GroqServiceError

router = APIRouter()


class AnalysisPayload(BaseModel):
    analysis: Dict[str, Any]


@router.post("/scenarios", response_model=ScenarioList)
async def scenarios_endpoint(payload: AnalysisPayload):
    """Generate test scenarios from analyzed page JSON using Groq AI.

    Input JSON shape: { "analysis": { ... } }
    Returns: { "scenarios": [ ... ] }
    """
    try:
        parsed = await generate_scenarios(payload.analysis)
    except GroqServiceError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error generating scenarios")

    # Ensure the output conforms to {"scenarios": [...]}
    if isinstance(parsed, dict) and "scenarios" in parsed:
        return parsed

    # If model returned a list (scenarios array), wrap it
    if isinstance(parsed, list):
        return {"scenarios": parsed}

    raise HTTPException(status_code=502, detail="Unexpected model output for scenarios")
