import os
import sys
from typing import TypedDict, Dict, Any, Optional
from langgraph.graph import StateGraph, END
import asyncpg
from mcp import ClientSession

# Append root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from backend.agents.document_understanding import document_understanding_node
from backend.agents.tool_nodes.chemical_normalization import chemical_normalization_node
from backend.agents.regulation_planning import regulation_planning_node
from backend.agents.compliance_screening import compliance_screening_node
from backend.agents.risk_and_decision import risk_and_decision_node
from backend.agents.report_generation import report_generation_node
from backend.graph.review_routing import review_routing_node, LOW_CONFIDENCE_THRESHOLD

class PipelineState(TypedDict):
    # Core orchestration inputs
    document_path: str
    workflow_run_id: str
    product_id: str
    db_pool: asyncpg.Pool
    mcp_client_a: ClientSession  # Chemical Identity MCP
    mcp_client_b: ClientSession  # Regulation Lookup MCP
    
    # Intermediate state tracking (Pydantic models converted to dicts for state passing)
    document_id: str
    applicable_regulations: Optional[list[Dict[str, str]]]
    compliance_decision_id: Optional[str]
    extraction_result: Optional[Dict[str, Any]]
    normalization_result: Optional[Dict[str, Any]]
    screening_result: Optional[Dict[str, Any]]
    decision_result: Optional[Dict[str, Any]]
    report_result: Optional[Dict[str, Any]]

def evaluate_confidence(state: PipelineState) -> str:
    """Evaluates if extraction or screening confidence is below threshold to trigger human review."""
    extraction_result = state.get("extraction_result", {})
    if extraction_result.get("extraction_confidence", 1.0) < LOW_CONFIDENCE_THRESHOLD:
        return "review_routing"
        
    screening_run = state.get("screening_result", {})
    results = screening_run.get("results", [])
    if any(r.get("confidence", 1.0) < LOW_CONFIDENCE_THRESHOLD for r in results):
        return "review_routing"
        
    return "risk_and_decision"

def build_pipeline_graph() -> StateGraph:
    """Builds and wires the strictly linear LangGraph for Phase 1 compliance screening."""
    graph = StateGraph(PipelineState)
    
    # Add nodes
    graph.add_node("document_understanding", document_understanding_node)
    graph.add_node("chemical_normalization", chemical_normalization_node)
    graph.add_node("regulation_planning", regulation_planning_node)
    graph.add_node("compliance_screening", compliance_screening_node)
    graph.add_node("risk_and_decision", risk_and_decision_node)
    graph.add_node("report_generation", report_generation_node)
    graph.add_node("review_routing", review_routing_node)
    
    # Wire edges
    graph.set_entry_point("document_understanding")
    graph.add_edge("document_understanding", "chemical_normalization")
    graph.add_edge("chemical_normalization", "regulation_planning")
    graph.add_edge("regulation_planning", "compliance_screening")
    
    # Conditional edge after screening
    graph.add_conditional_edges(
        "compliance_screening",
        evaluate_confidence,
        {
            "review_routing": "review_routing",
            "risk_and_decision": "risk_and_decision"
        }
    )
    
    # Branches terminate/converge
    graph.add_edge("review_routing", END)
    graph.add_edge("risk_and_decision", "report_generation")
    graph.add_edge("report_generation", END)
    
    return graph.compile()
