import os
import sys
import json
from typing import Dict, Any
import asyncpg
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI

# Append root path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from backend.schemas.state_schemas import ScreeningResult, ScreeningRunResult, ScreeningStatus
from backend.utils.telemetry import fire_and_forget_log

class BatchedLLMReasoning(BaseModel):
    tracking_id: int = Field(..., description="The unique integer ID provided for this evaluation")
    reasoning: str = Field(..., description="Explainability text why this status applies, citing threshold/exemption")

class BatchReasoningList(BaseModel):
    results: list[BatchedLLMReasoning]

async def compliance_screening_node(state: Dict[str, Any]) -> Dict[str, Any]:
    normalization_result = state.get("normalization_result")
    if not normalization_result:
        raise ValueError("Missing normalization_result in state")
        
    db_pool: asyncpg.Pool = state["db_pool"]
    mcp_client_b = state["mcp_client_b"]
    workflow_run_id = state["workflow_run_id"]
    product_id = state["product_id"]
    
    # Retrieve LLM
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set.")
    llm = ChatGoogleGenerativeAI(model="gemini-3.1-flash-lite", api_key=api_key, temperature=0.0)
    structured_llm = llm.with_structured_output(BatchReasoningList)
    
    screening_results_list = []
    applicable_regulations = state.get("applicable_regulations", [])
    # Extract just the codes from the state dicts
    regulations_to_check = [r["code"] for r in applicable_regulations] if applicable_regulations else []
    
    pending_explanations = []
    db_insert_records = []
    tracking_counter = 0
    
    async with db_pool.acquire() as conn:
        for comp in normalization_result.get("components", []):
            comp_name = comp["component_name"]
            
            # Get component_id
            comp_id = await conn.fetchval(
                "SELECT id FROM components WHERE product_id = $1 AND name = $2 LIMIT 1",
                product_id, comp_name
            )
            
            for ing in comp.get("ingredients", []):
                cas_number = ing.get("cas_number")
                canonical_name = ing.get("canonical_name")
                measured_val = ing.get("concentration_value")
                
                # Get ingredient_id
                if cas_number:
                    ing_id = await conn.fetchval("SELECT id FROM ingredients WHERE cas_number = $1 LIMIT 1", cas_number)
                else:
                    ing_id = await conn.fetchval("SELECT id FROM ingredients WHERE canonical_name = $1 LIMIT 1", canonical_name)
                    
                if not ing_id or not comp_id:
                    continue  # Should not happen given previous node
                
                for reg_code in regulations_to_check:
                    reg_id = await conn.fetchval("SELECT id FROM regulations WHERE code = $1 LIMIT 1", reg_code)
                    if not reg_id:
                        continue
                        
                    # Call Agent B
                    try:
                        mcp_res = await mcp_client_b.call_tool("get_thresholds_for_ingredient", arguments={"cas_number": cas_number, "regulation_code": reg_code})
                        threshold_data = json.loads(mcp_res.content[0].text)
                        fire_and_forget_log(db_pool, workflow_run_id, "MCP", "SUCCESS")
                    except Exception as e:
                        fire_and_forget_log(db_pool, workflow_run_id, "MCP", "FAILED")
                        threshold_data = {"status": "not_found"}
                        
                    status: ScreeningStatus = "ALLOWED"
                    threshold_val_raw = threshold_data.get("threshold_value")
                    threshold_val = float(threshold_val_raw) if threshold_val_raw is not None else None
                    exemption_notes = threshold_data.get("exemption_notes")
                    confidence = 1.0
                    reasoning = "No specific regulatory restrictions apply to this substance under the evaluated regulation."
                    
                    if threshold_data.get("status") == "not_found" or threshold_val is None:
                        status = "ALLOWED"
                    elif reg_code == "PROP_65":
                        status = "NEEDS_REVIEW"
                        confidence = 0.9
                        reasoning = "Prop 65 is exposure-based (MADL/NSRL). Concentration thresholds alone cannot determine compliance. The stored threshold is a schema-compatibility placeholder; manual exposure assessment is required."
                    else:
                        # Deterministic Python comparison
                        if measured_val is not None and measured_val > threshold_val:
                            if exemption_notes:
                                status = "EXEMPTION_AVAILABLE"
                                confidence = 0.8
                            else:
                                status = "THRESHOLD_EXCEEDED"
                        elif measured_val is not None and measured_val <= threshold_val:
                            status = "ALLOWED"
                        else:
                            # We have a threshold but no measured value
                            status = "NEEDS_REVIEW"
                            confidence = 0.5
                            
                    # Construct record to track state
                    record = {
                        "tracking_id": tracking_counter,
                        "comp_name": comp_name,
                        "cas_number": cas_number,
                        "canonical_name": canonical_name,
                        "reg_code": reg_code,
                        "status": status,
                        "measured_val": measured_val,
                        "threshold_val": threshold_val,
                        "confidence": confidence,
                        "reasoning": reasoning,
                        "workflow_run_id": workflow_run_id,
                        "comp_id": comp_id,
                        "ing_id": ing_id,
                        "reg_id": reg_id
                    }
                    
                    # Determine if LLM reasoning is needed
                    if reg_code != "PROP_65":
                        pending_explanations.append({
                            "tracking_id": tracking_counter,
                            "ingredient": canonical_name,
                            "cas": cas_number,
                            "measured": measured_val,
                            "regulation": reg_code,
                            "threshold": threshold_val,
                            "exemption_notes": exemption_notes,
                            "assigned_status": status
                        })
                    
                    db_insert_records.append(record)
                    tracking_counter += 1
                    
        # --- Batch LLM Execution ---
        # Chunk requests into sizes of 10 to avoid token limits
        CHUNK_SIZE = 10
        for i in range(0, len(pending_explanations), CHUNK_SIZE):
            chunk = pending_explanations[i:i+CHUNK_SIZE]
            
            prompt = f"""
You are a compliance reasoning engine. I have evaluated several ingredients against regulations.
For each evaluation below, provide a short, professional explainability sentence summarizing why its status was assigned.
Do not change the assigned status. Just explain it.

Evaluations:
{json.dumps(chunk, indent=2)}

Return a JSON array of objects matching the structured schema (tracking_id, reasoning).
"""
            try:
                llm_res = await structured_llm.ainvoke(prompt)
                fire_and_forget_log(db_pool, workflow_run_id, "LLM", "SUCCESS")
            except Exception as e:
                fire_and_forget_log(db_pool, workflow_run_id, "LLM", "FAILED")
                raise RuntimeError(f"LLM Reasoning failed for batch: {str(e)}")
                
            # 5-Point Validation
            returned_ids = [res.tracking_id for res in llm_res.results]
            expected_ids = [req["tracking_id"] for req in chunk]
            
            if len(returned_ids) != len(expected_ids):
                raise RuntimeError(f"Validation Error: Expected {len(expected_ids)} reasonings, got {len(returned_ids)}")
                
            if len(returned_ids) != len(set(returned_ids)):
                raise RuntimeError("Validation Error: Duplicate tracking_ids returned by LLM")
                
            missing_ids = set(expected_ids) - set(returned_ids)
            if missing_ids:
                raise RuntimeError(f"Validation Error: LLM dropped expected tracking_ids: {missing_ids}")
                
            unknown_ids = set(returned_ids) - set(expected_ids)
            if unknown_ids:
                raise RuntimeError(f"Validation Error: LLM hallucinated unknown tracking_ids: {unknown_ids}")
                
            # Map reasoning back
            for res in llm_res.results:
                if not res.reasoning or not isinstance(res.reasoning, str):
                    raise RuntimeError(f"Validation Error: Invalid reasoning text for tracking_id {res.tracking_id}")
                db_insert_records[res.tracking_id]["reasoning"] = res.reasoning

        # --- DB Persistence (Atomic) ---
        async with conn.transaction():
            for rec in db_insert_records:
                sr = ScreeningResult(
                    component_name=rec["comp_name"],
                    ingredient_cas_number=rec["cas_number"],
                    ingredient_canonical_name=rec["canonical_name"],
                    regulation_code=rec["reg_code"],
                    status=rec["status"],
                    measured_value=rec["measured_val"],
                    threshold_value=rec["threshold_val"],
                    confidence=rec["confidence"],
                    reasoning=rec["reasoning"]
                )
                screening_results_list.append(sr)
                
                await conn.execute(
                    """
                    INSERT INTO screening_results 
                    (workflow_run_id, component_id, ingredient_id, regulation_id, status, measured_value, threshold_value, confidence, reasoning)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    """,
                    rec["workflow_run_id"], rec["comp_id"], rec["ing_id"], rec["reg_id"], 
                    rec["status"], rec["measured_val"], rec["threshold_val"], 
                    rec["confidence"], rec["reasoning"]
                )
                    
    final_result = ScreeningRunResult(
        workflow_run_id=workflow_run_id,
        results=screening_results_list
    )
    
    return {"screening_result": final_result.model_dump()}
