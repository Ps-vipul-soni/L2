import os
import sys
import fitz  # PyMuPDF
from typing import Dict, Any
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))

# Append root path to allow importing backend schemas
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from backend.schemas.state_schemas import DocumentExtractionResult

def extract_pdf_text(file_path: str) -> str:
    """Extracts raw string text from a PDF file safely using PyMuPDF."""
    text = ""
    with fitz.open(file_path) as doc:
        for page in doc:
            text += page.get_text()
    return text

def document_understanding_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LangGraph node to extract structured DocumentExtractionResult from an SDS PDF.
    Expects state["pdf_path"] to contain the absolute path to the PDF.
    Returns state updated with "extraction_result".
    """
    try:
        pdf_path = state.get("pdf_path")
        if not pdf_path or not os.path.exists(pdf_path):
            raise FileNotFoundError(f"Invalid or missing pdf_path: {pdf_path}")
            
        # Extract raw text directly from the local PDF file
        raw_text = extract_pdf_text(pdf_path)
        
        # Securely retrieve Gemini API key
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set in the .env file or environment variables.")
            
        # Initialize the LLM (Using flash for speed, sufficient for structured extraction)
        llm = ChatGoogleGenerativeAI(
            model="gemini-3.1-flash-lite",
            api_key=api_key,
            temperature=0.0
        )
        
        # Enforce strict output mapping mathematically to DocumentExtractionResult
        structured_llm = llm.with_structured_output(DocumentExtractionResult)
        
        prompt = f"""
You are a regulatory compliance expert analyzing a Safety Data Sheet (SDS).
Your job is to read the raw PDF text below and extract the product information and exact chemical ingredients from Section 3 ("Composition/Information on Ingredients").

Constraints:
1. Extract the raw name exactly as it appears on the document.
2. Extract the CAS number if it is printed. Otherwise leave null.
3. Extract the concentration value and unit (%, ppm, mg/kg) if present. If it's a range, extract the upper bound. Prioritize numerical values.
4. Extract the overall product name and place it in product_name_hint.
5. Create a component representing the overall material and put the ingredients inside it.
6. The doc_type MUST be exactly "SDS".
7. Critically self-assess extraction_confidence (0.0 to 1.0). Be honest; if sections are blurry, ambiguous, or the composition is hidden as a trade secret, lower the score.
8. Use extraction_notes to explain any ambiguity or assumptions you made (e.g. taking the upper bound of a range).

Here is the raw text extracted from the PDF:
---
{raw_text}
---
"""
        
        # Run structured extraction
        result: DocumentExtractionResult = structured_llm.invoke(prompt)
        
        # Return updated state dictionary containing the fully compliant Pydantic dictionary
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
