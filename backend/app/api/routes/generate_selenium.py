from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.selenium_service import generate_selenium_bundle
from app.models.groq_models import SeleniumBundle
from app.core.groq_service import GroqServiceError

router = APIRouter()


class SeleniumPayload(BaseModel):
    testcases: Any
    testdata: Optional[Any] = None
    scenarios: Optional[Any] = None


@router.post("/generate-selenium", response_model=SeleniumBundle)
async def generate_selenium_endpoint(payload: SeleniumPayload):
    """Generate Selenium Python code from testcases and optional artifacts.

    Input: {
      "testcases": [ ... ],
      "testdata": { ... },
      "scenarios": [ ... ]
    }

    Output: {
      "files": {"page_objects/login_page.py": "...", "tests/test_login.py": "...", ...},
      "metadata": { ... }
    }
    """
    try:
        result = await generate_selenium_bundle(
            payload.testcases,
            testdata=payload.testdata,
            scenarios=payload.scenarios,
        )
    except GroqServiceError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error generating Selenium code")

    if isinstance(result, dict) and "files" in result:
        return result

    raise HTTPException(status_code=502, detail="Unexpected output from Selenium generator")
