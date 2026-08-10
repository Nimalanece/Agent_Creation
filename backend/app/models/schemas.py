from typing import Optional, Dict, Any
from pydantic import BaseModel

class AnalyzeOptions(BaseModel):
    render_js: Optional[bool] = False
    depth: Optional[int] = 1

class AnalyzeRequest(BaseModel):
    url: str
    options: Optional[AnalyzeOptions] = None

class AnalyzeResponse(BaseModel):
    run_id: str
    status: Optional[str] = "queued"

class RunRequest(BaseModel):
    run_id: Optional[str] = None
    url: Optional[str] = None
    options: Optional[Dict[str, Any]] = None

class GenericResponse(BaseModel):
    run_id: str
    status: Optional[str] = "queued"
