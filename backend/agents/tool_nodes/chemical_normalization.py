import os
import sys
import json

from typing import Dict, Any
import asyncpg
from backend.utils.telemetry import fire_and_forget_log

# Append root path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from backend.schemas.state_schemas import (
    NormalizedIngredient,
    NormalizedComponent,
    NormalizationResult
)

async def chemical_normalization_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Tool node (No LLM).
    1. Inserts the source document into the DB.
    2. Calls Chemical Identity MCP to normalize ingredients.
    3. Persists components and ingredients to the DB.
    """
    extraction_result = state.get("extraction_result")
    if not extraction_result:
        raise ValueError("Missing extraction_result in state")
        
    db_pool: asyncpg.Pool = state["db_pool"]
    mcp_client_a = state["mcp_client_a"]
    workflow_run_id = state.get("workflow_run_id")

    product_id = state["product_id"]
    
    document_ids = state.get("document_ids", [])
    
    async with db_pool.acquire() as conn:
        for doc_id in document_ids:
            conf_dict = extraction_result.get("extraction_confidence", {})
            if doc_id not in conf_dict:
                raise ValueError(f"document_id '{doc_id}' is missing from extraction_confidence mapping.")
            
            await conn.execute(
                """
                UPDATE documents 
                SET extraction_confidence = $1 
                WHERE id = $2
                """,
                conf_dict[doc_id],
                doc_id
            )
    
    normalized_components = []
    
    # 2 & 3. Normalize and Persist
    async with db_pool.acquire() as conn:
        # Start a transaction for the complex inserts
        async with conn.transaction():
            for extracted_comp in extraction_result.get("components", []):
                # Insert Component
                comp_id = await conn.fetchval(
                    """
                    INSERT INTO components (product_id, name)
                    VALUES ($1, $2)
                    RETURNING id
                    """,
                    product_id,
                    extracted_comp["component_name"]
                )
                
                normalized_ingredients = []
                
                for ext_ing in extracted_comp.get("ingredients", []):
                    raw_name = ext_ing["raw_name"]
                    
                    try:
                        # Call Agent A via MCP Client
                        mcp_res = await mcp_client_a.call_tool("resolve_ingredient", arguments={"name": raw_name})
                        
                        # The response content is typically JSON text inside the first content block
                        result_json = json.loads(mcp_res.content[0].text)
                        fire_and_forget_log(db_pool, workflow_run_id, "MCP", "SUCCESS")
                    except Exception as e:
                        fire_and_forget_log(db_pool, workflow_run_id, "MCP", "FAILED")
                        print(f"Error calling chemical normalization MCP: {e}")
                        result_json = {}
                    
                    # Merge concentration back in since MCP doesn't know about it
                    result_json["raw_name"] = raw_name
                    result_json["concentration_value"] = ext_ing.get("concentration_value")
                    result_json["concentration_unit"] = ext_ing.get("concentration_unit")
                    
                    norm_ing = NormalizedIngredient(**result_json)
                    normalized_ingredients.append(norm_ing)
                    
                    # Persist Ingredient (upsert on CAS if available, otherwise just insert)
                    cas_num = norm_ing.cas_number
                    if norm_ing.resolution_method != "unresolved" and cas_num:
                        ing_id = await conn.fetchval(
                            """
                            INSERT INTO ingredients (canonical_name, cas_number, pubchem_cid)
                            VALUES ($1, $2, $3)
                            ON CONFLICT (cas_number) DO UPDATE 
                            SET canonical_name = EXCLUDED.canonical_name, pubchem_cid = EXCLUDED.pubchem_cid
                            RETURNING id
                            """,
                            norm_ing.canonical_name, cas_num, norm_ing.pubchem_cid
                        )
                    else:
                        # Unresolved or missing CAS -> Insert new distinct ingredient
                        ing_id = await conn.fetchval(
                            """
                            INSERT INTO ingredients (canonical_name, pubchem_cid)
                            VALUES ($1, $2)
                            RETURNING id
                            """,
                            norm_ing.canonical_name, norm_ing.pubchem_cid
                        )
                    
                    # Upsert Synonym
                    await conn.execute(
                        """
                        INSERT INTO ingredient_synonyms (ingredient_id, raw_name)
                        VALUES ($1, $2)
                        ON CONFLICT (ingredient_id, raw_name) DO NOTHING
                        """,
                        ing_id, raw_name
                    )
                    
                    # Insert Component-Ingredient link
                    await conn.execute(
                        """
                        INSERT INTO component_ingredients 
                        (component_id, ingredient_id, concentration_value, concentration_unit, source_document_id)
                        VALUES ($1, $2, $3, $4, $5)
                        ON CONFLICT (component_id, ingredient_id, source_document_id) DO NOTHING
                        """,
                        comp_id, ing_id, norm_ing.concentration_value, norm_ing.concentration_unit, extracted_comp.get("source_document_id")
                    )
                
                normalized_components.append(NormalizedComponent(
                    component_name=extracted_comp["component_name"],
                    ingredients=normalized_ingredients,
                    source_document_id=extracted_comp.get("source_document_id")
                ))
    
    primary_doc_id = document_ids[0] if document_ids else ""
    normalization_result = NormalizationResult(
        document_id=primary_doc_id,
        components=normalized_components
    )
    
    return {
        "document_ids": document_ids,
        "normalization_result": normalization_result.model_dump()
    }
