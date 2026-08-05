import os
import sys
import json
from typing import Dict, Any
import asyncpg
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI

# Append root path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from backend.schemas.state_schemas import ComplianceDecision, OverallStatus

class DecisionModel(BaseModel):
    decision_rationale: str = Field(..., description="Short explanation of how overall_status and risk_score were derived from the screening results.")

async def risk_and_decision_node(state: Dict[str, Any]) -> Dict[str, Any]:
    screening_data = state.get("screening_result")
    if not screening_data:
        raise ValueError("Missing screening_result in state")
        
    db_pool: asyncpg.Pool = state["db_pool"]
    workflow_run_id = state["workflow_run_id"]
    product_id = state["product_id"]
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set.")
    llm = ChatGoogleGenerativeAI(model="gemini-3.1-flash-lite", api_key=api_key, temperature=0.0)
    structured_llm = llm.with_structured_output(DecisionModel)
    
    # Simple risk algorithm
    has_restricted = False
    has_exceeded = False
    has_review = False
    
    results = screening_data.get("results", [])
    for res in results:
        st = res["status"]
        if st == "RESTRICTED" or st == "THRESHOLD_EXCEEDED":
            has_exceeded = True
        elif st == "NEEDS_REVIEW" or st == "EXEMPTION_AVAILABLE":
            has_review = True
            
    if has_exceeded:
        overall_status = "FAIL"
        risk_score = 90.0
    elif has_review:
        overall_status = "WARNING"
        risk_score = 50.0
    else:
        overall_status = "PASS"
        risk_score = 10.0
        
    # Ask LLM to generate the rationale
    prompt = f"""
You are a compliance risk officer.
I have aggregated the following screening results into an overall status: {overall_status} and risk score: {risk_score}.
Summary of individual results:
{json.dumps([{ 'ingredient': r['ingredient_canonical_name'], 'status': r['status'] } for r in results], indent=2)}

Please provide a concise decision_rationale.
"""
    llm_res = structured_llm.invoke(prompt)
    
    decision = ComplianceDecision(
        workflow_run_id=workflow_run_id,
        product_id=product_id,
        overall_status=overall_status,
        risk_score=risk_score,
        decision_rationale=llm_res.decision_rationale
    )
    
    # Persist
    async with db_pool.acquire() as conn:
        decision_id = await conn.fetchval(
            """
            INSERT INTO compliance_decisions (workflow_run_id, product_id, overall_status, risk_score)
            VALUES ($1, $2, $3, $4)
            RETURNING id
            """,
            workflow_run_id, product_id, overall_status, risk_score
        )
        # Add decision_id to state since it's needed by Report Generation
        state["compliance_decision_id"] = str(decision_id)
        
    return {"decision_result": decision.model_dump(), "compliance_decision_id": str(decision_id)}
