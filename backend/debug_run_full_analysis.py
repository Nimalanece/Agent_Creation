import asyncio
import traceback

from dotenv import load_dotenv
from app.services.orchestrator_service import run_full_pipeline

load_dotenv()

async def main():
    try:
        result = await run_full_pipeline('https://www.saucedemo.com/')
        print(result)
    except Exception:
        traceback.print_exc()

asyncio.run(main())
