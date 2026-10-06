import logging
from typing import Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.orchestrator_service import run_full_pipeline
from app.services.url_analysis_service import URLAnalysisError
from app.core.groq_service import GroqServiceError
from app.models.schemas import Agent1PipelineResponse

router = APIRouter()
LOGGER = logging.getLogger(__name__)


class FullAnalysisRequest(BaseModel):
    url: str
    render_js: bool = False

@router.post("/full-analysis", response_model=Agent1PipelineResponse)
async def full_analysis_endpoint(payload: FullAnalysisRequest):
    """Run analysis pipeline: analyze -> scenarios -> testcases.
    Request: { "url": "https://example.com" }
    Response: {
      "analysis": {...},
      "scenarios": [...],
      "testcases": [...],
      "discovered_locators": {...}
    }
    """
    try:
        result = await run_full_pipeline(payload.url, render_js=payload.render_js)
        Agent1PipelineResponse.model_validate(result)
        return result
    except URLAnalysisError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except GroqServiceError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        LOGGER.exception("Full analysis failed for url=%s", payload.url)
        raise HTTPException(status_code=500, detail=f"Internal server error during full analysis: {e}") from e

