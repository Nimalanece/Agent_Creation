from typing import Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.orchestrator_service import run_full_pipeline
from app.services.url_analysis_service import URLAnalysisError
from app.core.groq_service import GroqServiceError

router = APIRouter()


class FullAnalysisRequest(BaseModel):
    url: str
    render_js: bool = False

@router.post("/full-analysis", response_model=Dict)
async def full_analysis_endpoint(payload: FullAnalysisRequest):
    """Run full pipeline: analyze -> scenarios -> testcases -> testdata -> selenium code
    Request: { "url": "https://example.com" }
    Response: {
      "analysis": {...},
      "scenarios": [...],
      "testcases": [...],
      "testdata": {...},
      "selenium_code": "<combined code>",
      "selenium_files": {"path": "code"}
    }
    """
    try:
        result = await run_full_pipeline(payload.url, render_js=payload.render_js)
    except URLAnalysisError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except GroqServiceError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error during full analysis")

    return result
