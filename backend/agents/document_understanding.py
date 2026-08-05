import os
import sys
from typing import Dict, Any

# Append root path to allow importing backend schemas
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from backend.schemas.state_schemas import DocumentExtractionResult
from backend.agents.document_parsers import PARSER_REGISTRY

def document_understanding_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LangGraph node to extract structured DocumentExtractionResult from documents.
    Supports PDF, CSV, Excel, and XML via format-specific parsers.
    Expects state["document_path"] to contain the absolute path to the document.
    Returns state updated with "extraction_result".
    """
    try:
        document_path = state.get("document_path")
        if not document_path or not os.path.exists(document_path):
            raise FileNotFoundError(f"Invalid or missing document_path: {document_path}")
            
        ext = os.path.splitext(document_path)[1].lower()
        
        parser_func = PARSER_REGISTRY.get(ext)
        if not parser_func:
            fallback = DocumentExtractionResult(
                doc_type="SDS",  # Default fallback
                product_name_hint=None,
                components=[],
                extraction_confidence=0.0,
                extraction_notes=f"Unsupported file format '{ext}'. Expected one of: {list(PARSER_REGISTRY.keys())}"
            )
            return {"extraction_result": fallback.model_dump()}
            
        # Execute the specific parser
        result: DocumentExtractionResult = parser_func(document_path)
        return {"extraction_result": result.model_dump()}
        
    except Exception as e:
        # Fallback to ensure the LangGraph node never crashes and always returns valid Pydantic JSON
        fallback = DocumentExtractionResult(
            doc_type="SDS",
            product_name_hint=None,
            components=[],
            extraction_confidence=0.0,
            extraction_notes=f"Extraction failed: {type(e).__name__} - {str(e)}"
        )
        return {"extraction_result": fallback.model_dump()}
