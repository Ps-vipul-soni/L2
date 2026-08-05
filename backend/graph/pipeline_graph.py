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
from backend.agents.compliance_screening import compliance_screening_node
from backend.agents.risk_and_decision import risk_and_decision_node
from backend.agents.report_generation import report_generation_node

class PipelineState(TypedDict):
    # Core orchestration inputs
    pdf_path: str
    workflow_run_id: str
    product_id: str
    db_pool: asyncpg.Pool
    mcp_client_a: ClientSession  # Chemical Identity MCP
    mcp_client_b: ClientSession  # Regulation Lookup MCP
    
    # Intermediate state tracking (Pydantic models converted to dicts for state passing)
    document_id: Optional[str]
    compliance_decision_id: Optional[str]
    extraction_result: Optional[Dict[str, Any]]
    normalization_result: Optional[Dict[str, Any]]
    screening_result: Optional[Dict[str, Any]]
    decision_result: Optional[Dict[str, Any]]
    report_result: Optional[Dict[str, Any]]

def build_pipeline_graph() -> StateGraph:
    """Builds and wires the strictly linear LangGraph for Phase 1 compliance screening."""
    graph = StateGraph(PipelineState)
    
    # Add nodes
    graph.add_node("document_understanding", document_understanding_node)
    graph.add_node("chemical_normalization", chemical_normalization_node)
    graph.add_node("compliance_screening", compliance_screening_node)
    graph.add_node("risk_and_decision", risk_and_decision_node)
    graph.add_node("report_generation", report_generation_node)
    
    # Wire edges sequentially
    graph.set_entry_point("document_understanding")
    graph.add_edge("document_understanding", "chemical_normalization")
    graph.add_edge("chemical_normalization", "compliance_screening")
    graph.add_edge("compliance_screening", "risk_and_decision")
    graph.add_edge("risk_and_decision", "report_generation")
    graph.add_edge("report_generation", END)
    
    return graph.compile()
