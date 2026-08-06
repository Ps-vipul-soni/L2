import os
import sys
import json
from typing import Dict, Any
import asyncpg
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

# Append root path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from backend.schemas.state_schemas import ScreeningResult, ScreeningRunResult, ScreeningStatus

class LLMReasoning(BaseModel):
    reasoning: str = Field(..., description="Explainability text why this status applies, citing threshold/exemption")

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
    structured_llm = llm.with_structured_output(LLMReasoning)
    
    screening_results_list = []
    applicable_regulations = state.get("applicable_regulations", [])
    # Extract just the codes from the state dicts
    regulations_to_check = [r["code"] for r in applicable_regulations] if applicable_regulations else []
    
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
                    if cas_number:
                        mcp_res = await mcp_client_b.call_tool("get_thresholds_for_ingredient", arguments={"cas_number": cas_number, "regulation_code": reg_code})
                        threshold_data = json.loads(mcp_res.content[0].text)
                    else:
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
                            
                    # Ask LLM for reasoning only if not already set (e.g. bypass for PROP_65)
                    if reg_code != "PROP_65":
                        prompt = f"""
You are a compliance reasoning engine. I have evaluated an ingredient against a regulation.
Ingredient: {canonical_name} (CAS: {cas_number})
Measured: {measured_val}
Regulation: {reg_code}
Threshold: {threshold_val}
Exemption Notes: {exemption_notes}
Assigned Status: {status}

Provide a short, professional explainability sentence summarizing why this status was assigned.
Do not change the status. Just explain it.
"""
                        llm_res = structured_llm.invoke(prompt)
                        reasoning = llm_res.reasoning
                    
                    # Construct ScreeningResult
                    sr = ScreeningResult(
                        component_name=comp_name,
                        ingredient_cas_number=cas_number,
                        ingredient_canonical_name=canonical_name,
                        regulation_code=reg_code,
                        status=status,
                        measured_value=measured_val,
                        threshold_value=threshold_val,
                        confidence=confidence,
                        reasoning=reasoning
                    )
                    screening_results_list.append(sr)
                    
                    # Persist
                    await conn.execute(
                        """
                        INSERT INTO screening_results 
                        (workflow_run_id, component_id, ingredient_id, regulation_id, status, measured_value, threshold_value, confidence, reasoning)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                        """,
                        workflow_run_id, comp_id, ing_id, reg_id, status, measured_val, threshold_val, confidence, reasoning
                    )
                    
    final_result = ScreeningRunResult(
        workflow_run_id=workflow_run_id,
        results=screening_results_list
    )
    
    return {"screening_result": final_result.model_dump()}
