from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import analyze, scenarios, testcases, full_analysis, testdata, selenium

app = FastAPI(
    title="AI QA Agent - Backend",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# NOTE: tighten origins in production
origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers under /api
app.include_router(analyze.router, prefix="/api")
app.include_router(scenarios.router, prefix="/api")
app.include_router(testcases.router, prefix="/api")
app.include_router(full_analysis.router, prefix="/api")
app.include_router(testdata.router, prefix="/api")
app.include_router(selenium.router, prefix="/api")


@app.get("/")
async def root():
    return {"service": "ai-qa-backend", "status": "ok"}
