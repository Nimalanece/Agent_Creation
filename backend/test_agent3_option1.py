#!/usr/bin/env python3
"""
Test Agent3 with Option 1: Pass agent_2_contract to auto-extract test_data

Usage:
  1. Run /full-analysis first to get the complete response
  2. Copy the test_case, application_url, and agent_2_contract from the response
  3. Update the payload below with your actual data
  4. Run this script
"""

import asyncio
import json
import httpx


async def test_agent3_with_option1():
    """
    Test Agent3 endpoint with Option 1: passing agent_2_contract for auto-extraction
    """
    
    # Step 1: Call full-analysis to get agent_2_contract and test_case
    print("=" * 80)
    print("STEP 1: Running full-analysis...")
    print("=" * 80)
    
    async with httpx.AsyncClient() as client:
        full_analysis_response = await client.post(
            "http://localhost:8000/api/full-analysis",
            json={"url": "https://demoqa.com/automation-practice-form"},
            timeout=30.0,
        )
        
        if full_analysis_response.status_code != 200:
            print(f"❌ Full-analysis failed: {full_analysis_response.status_code}")
            print(full_analysis_response.text)
            return
        
        full_analysis = full_analysis_response.json()
        print(f"✅ Full-analysis successful")
        
        # Step 2: Extract the parts we need for Agent3
        print("\n" + "=" * 80)
        print("STEP 2: Preparing Agent3 request with Option 1...")
        print("=" * 80)
        
        # Get first test case from the response
        testcases = full_analysis.get("testcases", [])
        agent_2_contract = full_analysis.get("agent_2_contract", {})
        application_url = full_analysis.get("application_url", "")
        
        if not testcases:
            print("❌ No test cases in full-analysis response")
            return
        
        test_case = testcases[0]
        print(f"Using test case: {test_case.get('title', 'N/A')}")
        print(f"Test case keys: {list(test_case.keys())}")
        
        # Step 3: Build Agent3 request with Option 1
        agent3_payload = {
            "test_case": test_case,
            "test_data": {},  # Empty - Option 1 will auto-extract from agent_2_contract
            "application_url": application_url,
            "agent_2_contract": agent_2_contract,
        }
        
        print(f"agent_2_contract keys: {list(agent_2_contract.keys())}")
        print(f"agent_2_contract.positive_data count: {len(agent_2_contract.get('positive_data', []))}")
        
        # Log what will be extracted
        positive_data = agent_2_contract.get("positive_data", [])
        if positive_data:
            first_dataset = positive_data[0]
            generated_data = first_dataset.get("generated_data", {})
            print(f"Will auto-extract test_data with keys: {list(generated_data.keys())}")
        
        # Step 4: Call Agent3
        print("\n" + "=" * 80)
        print("STEP 3: Calling Agent3 /generate-selenium with Option 1...")
        print("=" * 80)
        
        agent3_response = await client.post(
            "http://localhost:8000/api/agent3/generate-selenium",
            json=agent3_payload,
            timeout=60.0,
        )
        
        print(f"Response status: {agent3_response.status_code}")
        
        if agent3_response.status_code == 200:
            result = agent3_response.json()
            code = result.get("code", "")
            print(f"✅ SUCCESS! Generated Selenium code ({len(code)} characters)")
            print("\n" + "=" * 80)
            print("Generated Code:")
            print("=" * 80)
            print(code[:500])  # Print first 500 chars
            if len(code) > 500:
                print(f"... ({len(code) - 500} more characters)")
        else:
            print(f"❌ Agent3 failed: {agent3_response.status_code}")
            print(agent3_response.text)


if __name__ == "__main__":
    asyncio.run(test_agent3_with_option1())
