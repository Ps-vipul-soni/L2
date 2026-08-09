import os
import json
from typing import Dict, Any
import asyncpg
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

class LLMProductMatch(BaseModel):
    matches: bool = Field(..., description="True if the product type falls under the regulation's applicable product types")
    reasoning: str = Field(..., description="Short explanation why")

from backend.utils.matching import check_string_match, check_jurisdiction

async def regulation_planning_node(state: Dict[str, Any]) -> Dict[str, Any]:
    db_pool: asyncpg.Pool = state["db_pool"]
    product_id = state["product_id"]
    
    # Retrieve LLM
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set.")
    llm = ChatGoogleGenerativeAI(model="gemini-3.1-flash-lite", api_key=api_key, temperature=0.0)
    structured_llm = llm.with_structured_output(LLMProductMatch)
    
    applicable_regulations = []
    
    async with db_pool.acquire() as conn:
        product = await conn.fetchrow("SELECT product_type, market_country, customer_name FROM products WHERE id = $1", product_id)
        if not product:
            raise ValueError(f"Product {product_id} not found")
            
        p_type = product['product_type']
        p_country = product['market_country']
        p_customer = product['customer_name']
        
        regs = await conn.fetch("SELECT code, jurisdiction, applies_to_product_types, customer_name FROM regulations")
        
        for reg in regs:
            code = reg['code']
            r_juris = reg['jurisdiction']
            r_types = reg['applies_to_product_types']
            r_cust = reg['customer_name']
            
            # 1. Customer Check
            if r_cust and r_cust != p_customer:
                continue
                
            # 2. Jurisdiction Check
            if not check_jurisdiction(p_country, r_juris):
                continue
                
            # 3. Product Type Check
            matched_on = []
            if r_cust == p_customer and p_customer is not None:
                matched_on.append(f"customer_name={r_cust}")
            
            if r_juris == 'Global':
                matched_on.append("jurisdiction=Global")
            elif check_jurisdiction(p_country, r_juris):
                matched_on.append(f"market_country={r_juris}")
                
            # Product type evaluation
            is_type_match = False
            if not r_types:
                is_type_match = True
                matched_on.append("product_type=ANY")
            else:
                # Deterministic check
                if check_string_match(p_type, r_types):
                    is_type_match = True
                    matched_on.append(f"product_type={p_type}")
                else:
                    # Fallback to LLM for fuzzy/ambiguous product types
                    if p_type:
                        prompt = f"""
Does the product type '{p_type}' logically fall into any of these regulatory categories: {r_types}?
Consider industry standards and common sense (e.g. 'smartwatch' is 'electronics', 't-shirt' is 'apparel').
"""
                        res = structured_llm.invoke(prompt)
                        if res.matches:
                            is_type_match = True
                            matched_on.append(f"product_type_fuzzy={p_type} (LLM: {res.reasoning})")
                            
            if is_type_match:
                applicable_regulations.append({
                    "code": code,
                    "matched_on": ", ".join(matched_on)
                })

    return {"applicable_regulations": applicable_regulations}
