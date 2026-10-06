from fastapi import APIRouter, HTTPException
import logging

from app.core.gemini_service import GeminiService, GeminiServiceError
from app.models.schemas import Agent3GenerationRequest, Agent3GenerationResponse

router = APIRouter()
LOGGER = logging.getLogger(__name__)


@router.post("/agent3/generate-selenium", response_model=Agent3GenerationResponse)
async def generate_selenium(payload: Agent3GenerationRequest):
    # Log incoming request details for debugging metadata errors
    test_case = payload.test_case or {}
    test_data = payload.test_data or {}
    
    # Diagnostic: Log what we received
    LOGGER.info(
        "Agent3 STEP 1: Request received - test_data_provided=%s agent_2_contract_provided=%s",
        len(test_data) > 0,
        payload.agent_2_contract is not None,
    )
    
    # Priority 1: Use provided test_data if not empty
    if test_data and isinstance(test_data, dict) and test_data.get("generated_data"):
        LOGGER.info(
            "Agent3 STEP 2: Using supplied test_data - keys: %s",
            list(test_data.keys()),
        )
    # Priority 2: Try to extract from agent_2_contract (fallback from orchestrator)
    elif payload.agent_2_contract:
        LOGGER.info("Agent3 STEP 2: test_data empty, attempting auto-extraction from agent_2_contract...")
        test_data = {}
        contract = payload.agent_2_contract
        
        if not isinstance(contract, dict):
            LOGGER.error("  ❌ agent_2_contract is not a dict: %s", type(contract).__name__)
        else:
            LOGGER.debug("  agent_2_contract keys: %s", list(contract.keys()))
            
            # Prefer the complete per-scenario bundle. Category datasets are
            # field-specific and can otherwise select the wrong scenario or
            # drop the other fields from the generated script.
            scenario_id = str(test_case.get("scenario_id") or test_case.get("id") or "").strip()
            scenario_outputs = contract.get("scenario_outputs") or []
            if isinstance(scenario_outputs, list):
                matching_output = next(
                    (
                        output for output in scenario_outputs
                        if isinstance(output, dict)
                        and str(output.get("scenario_id") or "").strip() == scenario_id
                    ),
                    None,
                )
                if matching_output and isinstance(matching_output.get("generated_data"), dict):
                    test_data = {
                        "scenario_id": matching_output.get("scenario_id"),
                        "requires_test_data": matching_output.get("requires_test_data", True),
                        "generated_data": matching_output["generated_data"],
                    }
                    LOGGER.info(
                        "Agent3 STEP 2 SUCCESS: Extracted complete scenario_outputs bundle for scenario_id=%s",
                        scenario_id,
                    )

            # Fall back to category records only when no complete scenario
            # output was available.
            extraction_attempted = False
            if test_data:
                extraction_attempted = True
            for data_category in ["positive_data", "negative_data", "boundary_data", "validation_data"]:
                if test_data:
                    break
                data_list = contract.get(data_category) or []
                data_count = len(data_list) if isinstance(data_list, list) else 0
                LOGGER.debug("    %s: %d entries (type=%s)", data_category, data_count, type(data_list).__name__)
                
                if data_list and isinstance(data_list, list) and len(data_list) > 0:
                    extraction_attempted = True
                    first_dataset = next(
                        (
                            dataset for dataset in data_list
                            if isinstance(dataset, dict)
                            and (
                                not scenario_id
                                or str(dataset.get("scenario_id") or "").strip() == scenario_id
                            )
                        ),
                        None,
                    )
                    if first_dataset is None:
                        continue
                    LOGGER.debug("      first entry type: %s", type(first_dataset).__name__)
                    
                    if isinstance(first_dataset, dict):
                        first_dataset_keys = list(first_dataset.keys())
                        LOGGER.debug("      first entry keys: %s", first_dataset_keys)
                        
                        generated_data = first_dataset.get("generated_data") or {}
                        generated_data_keys = list(generated_data.keys()) if isinstance(generated_data, dict) else []
                        LOGGER.debug("      generated_data type: %s, keys: %s", type(generated_data).__name__, generated_data_keys)
                        
                        if generated_data and isinstance(generated_data, dict):
                            test_data = {
                                "scenario_id": first_dataset.get("scenario_id"),
                                "requires_test_data": contract.get("requires_test_data", True),
                                "generated_data": generated_data,
                            }
                            LOGGER.info(
                                "✅ Agent3 STEP 2 SUCCESS: Auto-extracted test_data from %s[0]",
                                data_category,
                            )
                            LOGGER.info(
                                "  extracted: scenario_id=%s, requires_test_data=%s, generated_data_keys=%s",
                                first_dataset.get("scenario_id"),
                                contract.get("requires_test_data"),
                                generated_data_keys,
                            )
                            break
            
            if len(test_data) == 0 and extraction_attempted:
                LOGGER.warning("⚠️  Agent3 STEP 2 FAILED: Could not find generated_data in any category despite iteration")
            elif len(test_data) == 0:
                LOGGER.warning("⚠️  Agent3 STEP 2 FAILED: No data categories found in agent_2_contract")
    else:
        LOGGER.warning("Agent3 STEP 2: No test_data provided and no agent_2_contract available for extraction")
    
    LOGGER.info(
        "Agent3 STEP 3: Final validation - test_case_keys=%s test_data_keys=%s",
        list(test_case.keys()) if isinstance(test_case, dict) else type(test_case).__name__,
        list(test_data.keys()) if isinstance(test_data, dict) else type(test_data).__name__,
    )
    
    if isinstance(test_data, dict) and "generated_data" in test_data:
        LOGGER.info(
            "Agent3 STEP 3: test_data structure - has generated_data with keys: %s",
            list(test_data.get("generated_data", {}).keys()),
        )
    
    try:
        code = await GeminiService().generate_selenium_code(
            payload.test_case,
            test_data,
            payload.application_url,
        )
        return Agent3GenerationResponse(
            scenario_id=payload.test_case.get("scenario_id"),
            code=code,
        )
    except GeminiServiceError as exc:
        if str(exc).startswith("ERROR:"):
            raise HTTPException(
                status_code=422,
                detail={"error": "Agent 3 input validation failed", "message": str(exc)},
            ) from exc
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Agent 3 failed to generate Selenium code") from exc