import pandas as pd
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from backend.schemas.state_schemas import DocumentExtractionResult, ExtractedComponent, ExtractedIngredient

from backend.utils.telemetry import fire_and_forget_log

def extract_number_and_unit(val):
    if pd.isna(val):
        return None, None
    s = str(val).lower().strip()
    # Simple extraction (naive)
    unit = None
    if '%' in s or 'percent' in s:
        unit = '%'
    elif 'ppm' in s:
        unit = 'ppm'
    elif 'mg/kg' in s:
        unit = 'mg/kg'
    
    # Try parsing number
    import re
    # Match numbers (including decimals), take the highest if it's a range like "10-20"
    nums = re.findall(r"[-+]?\d*\.\d+|\d+", s)
    if nums:
        # Take the maximum number found in the string to be conservative
        num = max([float(n) for n in nums])
        return num, unit
    return None, unit

async def parse_bom(document_path: str, db_pool=None, workflow_run_id=None) -> DocumentExtractionResult:
    """Parses a CSV or Excel BOM document using Pandas with LLM fallback for ambiguous headers."""
    ext = os.path.splitext(document_path)[1].lower()
    
    if ext == '.csv':
        df = pd.read_csv(document_path)
    else:
        df = pd.read_excel(document_path)
        
    df.columns = [str(c).lower().strip() for c in df.columns]
    
    # Map common column headers
    component_col = next((c for c in df.columns if 'component' in c or 'part' in c), None)
    ingredient_col = next((c for c in df.columns if 'ingredient' in c or 'material' in c or 'substance' in c or 'chemical' in c), None)
    cas_col = next((c for c in df.columns if 'cas' in c), None)
    conc_col = next((c for c in df.columns if 'concentration' in c or 'percent' in c or 'amount' in c or 'qty' in c or '%' in c), None)
    
    # If we can't find the basic ingredient column, fallback to LLM
    if not ingredient_col:
        return await fallback_to_llm(df.to_csv(index=False), db_pool, workflow_run_id)
        
    components_map = {}
    
    for _, row in df.iterrows():
        raw_name = str(row[ingredient_col]).strip() if pd.notna(row[ingredient_col]) else None
        if not raw_name or raw_name.lower() == 'nan':
            continue
            
        cas_num = str(row[cas_col]).strip() if cas_col and pd.notna(row[cas_col]) else None
        if cas_num and cas_num.lower() == 'nan':
            cas_num = None
            
        conc_val, conc_unit = None, None
        if conc_col and pd.notna(row[conc_col]):
            conc_val, conc_unit = extract_number_and_unit(row[conc_col])
            
        comp_name = str(row[component_col]).strip() if component_col and pd.notna(row[component_col]) else "Main Product"
        if comp_name.lower() == 'nan':
            comp_name = "Main Product"
            
        ing = ExtractedIngredient(
            raw_name=raw_name,
            cas_number=cas_num,
            concentration_value=conc_val,
            concentration_unit=conc_unit
        )
        
        if comp_name not in components_map:
            components_map[comp_name] = ExtractedComponent(component_name=comp_name, ingredients=[])
        components_map[comp_name].ingredients.append(ing)

    return DocumentExtractionResult(
        doc_type="BOM",
        product_name_hint=None,
        components=list(components_map.values()),
        extraction_confidence={"unknown": 0.9},  # High confidence since it's tabular
        extraction_notes="Deterministically parsed via pandas"
    )

async def fallback_to_llm(csv_text: str, db_pool=None, workflow_run_id=None) -> DocumentExtractionResult:
    """Uses Gemini to extract structured info if columns are too ambiguous."""
    try:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set in the environment.")
            
        llm = ChatGoogleGenerativeAI(model="gemini-3.1-flash-lite", api_key=api_key, temperature=0.0)
        structured_llm = llm.with_structured_output(DocumentExtractionResult)
        
        prompt = f"""
You are a compliance expert parsing a Bill of Materials (BOM) file in CSV format. 
The column headers were too ambiguous for deterministic parsing. 
Extract the components, ingredients, CAS numbers, and concentrations into the schema.
Set doc_type exactly to "BOM".
Objectively score extraction_confidence from 0.0 to 1.0 based strictly on extraction quality, completeness, clarity, and ambiguity. Do not default to any specific number.
Format extraction_confidence as a dictionary with the key "unknown" (e.g. {{"unknown": 0.85}}).

CSV Text:
{csv_text}
"""
        res = await structured_llm.ainvoke(prompt)
        fire_and_forget_log(db_pool, workflow_run_id, "LLM", "SUCCESS")
        return res
    except Exception as e:
        fire_and_forget_log(db_pool, workflow_run_id, "LLM", "FAILED")
        return DocumentExtractionResult(
            doc_type="BOM",
            product_name_hint=None,
            components=[],
            extraction_confidence={"unknown": 0.0},
            extraction_notes=f"LLM Fallback failed: {type(e).__name__} - {str(e)}"
        )
