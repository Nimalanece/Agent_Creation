import asyncio
import traceback

from app.services.orchestrator_service import run_full_pipeline

async def main():
    try:
        result = await run_full_pipeline('https://demoqa.com/text-box')
        print('SUCCESS', list(result.keys()))
        print('scenarios_count', len(result.get('scenarios', [])))
        print('analysis_counts', result.get('analysis', {}).get('counts'))
    except Exception:
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(main())
