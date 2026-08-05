import os
import fitz  # PyMuPDF
from langchain_google_genai import ChatGoogleGenerativeAI
from backend.schemas.state_schemas import DocumentExtractionResult

def extract_pdf_text(file_path: str) -> str:
    """Extracts raw string text from a PDF file safely using PyMuPDF."""
    text = ""
    with fitz.open(file_path) as doc:
        for page in doc:
            text += page.get_text()
    return text

def parse_sds(document_path: str) -> DocumentExtractionResult:
    """Parses an SDS PDF document using Gemini."""
    # Extract raw text directly from the local PDF file
    raw_text = extract_pdf_text(document_path)
    
    # Securely retrieve Gemini API key
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set in the .env file or environment variables.")
        
    # Initialize the LLM
    llm = ChatGoogleGenerativeAI(
        model="gemini-3.1-flash-lite",
        api_key=api_key,
        temperature=0.0
    )
    
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
    return structured_llm.invoke(prompt)
