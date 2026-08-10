from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Iterator

router = APIRouter()


class CodePayload(BaseModel):
    code: str


def _iter_code(code_str: str) -> Iterator[bytes]:
    # Stream the code in one chunk; could be chunked for large files
    yield code_str.encode("utf-8")


@router.post("/download-selenium")
async def download_selenium_endpoint(payload: CodePayload):
    """Return the provided code as a downloadable Python file named test_generated.py"""
    if not payload.code:
        raise HTTPException(status_code=400, detail="No code provided")

    headers = {
        "Content-Disposition": "attachment; filename=\"test_generated.py\"",
        "Content-Type": "text/x-python",
    }

    return StreamingResponse(_iter_code(payload.code), headers=headers)
