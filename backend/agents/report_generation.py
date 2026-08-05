import os
import sys
import json
from typing import Dict, Any
import asyncpg
from langchain_google_genai import ChatGoogleGenerativeAI

# Append root path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from backend.schemas.state_schemas import ComplianceReport

async def report_generation_node(state: Dict[str, Any]) -> Dict[str, Any]:
    decision_data = state.get("decision_result")
    screening_data = state.get("screening_result")
    
    if not decision_data or not screening_data:
        raise ValueError("Missing decision_result or screening_result in state")
        
    db_pool: asyncpg.Pool = state["db_pool"]
    workflow_run_id = state["workflow_run_id"]
    compliance_decision_id = state.get("compliance_decision_id")
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set.")
    llm = ChatGoogleGenerativeAI(model="gemini-3.1-flash-lite", api_key=api_key, temperature=0.0)
    structured_llm = llm.with_structured_output(ComplianceReport)
    
    prompt = f"""
You are a compliance report generator. Based on the following screening and decision data, generate a comprehensive ComplianceReport object.

Decision Data:
{json.dumps(decision_data, indent=2)}

Screening Data:
{json.dumps(screening_data, indent=2)}

Ensure the compliance_decision_id is '{compliance_decision_id}' and workflow_run_id is '{workflow_run_id}'.
"""
    report_res: ComplianceReport = structured_llm.invoke(prompt)
    
    # Save the markdown report to disk
    report_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../reports_output'))
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, f"report_{workflow_run_id}.md")
    
    markdown_content = f"""# Compliance Report
**Status:** {decision_data['overall_status']}
**Risk Score:** {decision_data['risk_score']}

## Executive Summary
{report_res.executive_summary}

## Violation Summary
{report_res.violation_summary}

## Risk Analysis
{report_res.risk_analysis}

## Affected Ingredients
{', '.join(report_res.affected_ingredients)}
"""
    with open(report_path, "w") as f:
        f.write(markdown_content)
        
    # Persist
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO reports (workflow_run_id, compliance_decision_id, executive_summary, file_path)
            VALUES ($1, $2, $3, $4)
            """,
            workflow_run_id, compliance_decision_id, report_res.executive_summary, report_path
        )
        
    return {"report_result": report_res.model_dump()}
