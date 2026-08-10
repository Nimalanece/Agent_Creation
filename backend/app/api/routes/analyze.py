from fastapi import APIRouter, HTTPException
from app.models.schemas import AnalyzeRequest, AnalyzeResponse
from app.services.analysis_service import analyze_page

router = APIRouter()

@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_endpoint(payload: AnalyzeRequest):
    """Placeholder endpoint to accept a URL and start analysis pipeline.
    Business logic not implemented yet; this calls a placeholder service.
    """
    try:
        result = await analyze_page(payload.url, options=payload.options)
    except NotImplementedError:
        raise HTTPException(status_code=501, detail="Not implemented")

    return AnalyzeResponse(run_id=result.get("run_id"), status=result.get("status", "queued"))
