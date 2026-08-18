import os
import sys
from typing import Dict, Any

# Append root path to allow importing backend schemas
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from backend.schemas.state_schemas import DocumentExtractionResult
from backend.agents.document_parsers import PARSER_REGISTRY

async def document_understanding_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LangGraph node to extract structured DocumentExtractionResult from documents.
    Supports PDF, CSV, Excel, and XML via format-specific parsers.
    Expects state["document_paths"] and state["document_ids"].
    Returns state updated with "extraction_result".
    """
    document_paths = state.get("document_paths", [])
    document_ids = state.get("document_ids", [])
    
    if not document_paths or not document_ids or len(document_paths) != len(document_ids):
        fallback = DocumentExtractionResult(
            doc_type="SDS",
            product_name_hint=None,
            components=[],
            extraction_confidence={"unknown": 0.0},
            extraction_notes="Invalid document_paths or document_ids state."
        )
        return {"extraction_result": fallback.model_dump()}

    all_components = []
    document_confidences: dict[str, float] = {}
    all_notes = []

    for doc_path, doc_id in zip(document_paths, document_ids):
        try:
            if not os.path.exists(doc_path):
                raise FileNotFoundError(f"Missing document_path: {doc_path}")
                
            ext = os.path.splitext(doc_path)[1].lower()
            parser_func = PARSER_REGISTRY.get(ext)
            
            if not parser_func:
                document_confidences[doc_id] = 0.0
                all_notes.append(f"[{doc_id}]: Unsupported file format '{ext}'")
                continue
                
            db_pool = state.get("db_pool")
            workflow_run_id = state.get("workflow_run_id")
            result: DocumentExtractionResult = await parser_func(doc_path, db_pool=db_pool, workflow_run_id=workflow_run_id)
            
            # Tag components with source document ID
            for comp in result.components:
                comp.source_document_id = doc_id
                all_components.append(comp)
                
            conf_score = 0.0
            if result.extraction_confidence:
                conf_score = list(result.extraction_confidence.values())[0]
            document_confidences[doc_id] = conf_score
                
            if result.extraction_notes:
                all_notes.append(f"[{doc_id}]: {result.extraction_notes}")
                
        except Exception as e:
            document_confidences[doc_id] = 0.0
            all_notes.append(f"[{doc_id}]: Extraction failed: {type(e).__name__} - {str(e)}")

    final_result = DocumentExtractionResult(
        doc_type="SDS",  # Defaulting, since this is a merged result
        product_name_hint=None,
        components=all_components,
        extraction_confidence=document_confidences,
        extraction_notes=" | ".join(all_notes) if all_notes else None
    )
    
    return {"extraction_result": final_result.model_dump()}
