import httpx
import json
import asyncio

async def test_full_analysis():
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get("http://localhost:8000/full-analysis?url=https://saucedemo.com", timeout=30)
            print(f"Status Code: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                
                # Check agent_3_input testcases
                testcases = result.get('agent_1_contract', {}).get('agent_3_input', {}).get('test_cases', [])
                print(f"Number of testcases: {len(testcases)}")
                
                if testcases:
                    tc = testcases[0]
                    print(f"First testcase application_url: {tc.get('application_url')}")
                    print(f"First testcase title: {tc.get('title')}")
                    print(f"First testcase expected_results: {tc.get('expected_results')}")
                    print(f"First testcase expected_result: {tc.get('expected_result')}")
                    print(f"\nAll fields in first testcase: {list(tc.keys())}")
            else:
                print(f"Error response: {response.text[:500]}")
        except Exception as e:
            print(f"Error: {e}")

asyncio.run(test_full_analysis())
