from fastapi import APIRouter, HTTPException, Request
from typing import List, Dict, Any

router = APIRouter()

@router.get("/suppliers/risk")
async def get_supplier_risk(request: Request):
    neo4j_driver = getattr(request.app.state, 'neo4j_driver', None)
    if not neo4j_driver:
        raise HTTPException(status_code=500, detail="Neo4j driver not initialized")
        
    # Phase 1: Batched Neo4j query
    # We want ALL suppliers. Get all suppliers and their distinct ingredient UUIDs.
    async with neo4j_driver.session() as session:
        result = await session.run("""
            MATCH (s:Supplier)
            OPTIONAL MATCH (s)<-[:SOURCED_FROM]-(c:Component)-[:USES]->(i:Ingredient)
            RETURN s.pg_id AS supplier_id, s.name AS supplier_name,
                   collect(DISTINCT i.pg_id) AS ingredient_ids
        """)
        records = await result.data()
        
    # Phase 2: Collect all ingredient IDs for a single batched Postgres query
    all_ingredient_ids = set()
    for rec in records:
        for i_id in rec["ingredient_ids"]:
            if i_id:
                all_ingredient_ids.add(i_id)
                
    flagged_ingredients_by_id = {}
    if all_ingredient_ids:
        # One batched query to Postgres
        pool = request.app.state.pool
        async with pool.acquire() as conn:
            pg_results = await conn.fetch("""
                SELECT sr.ingredient_id, i.canonical_name, r.code as regulation_code, sr.status
                FROM screening_results sr
                JOIN ingredients i ON sr.ingredient_id = i.id
                JOIN regulations r ON sr.regulation_id = r.id
                WHERE sr.ingredient_id = ANY($1::uuid[])
                  AND sr.status IN ('RESTRICTED', 'THRESHOLD_EXCEEDED')
            """, list(all_ingredient_ids))
            
            for row in pg_results:
                ing_id = str(row["ingredient_id"])
                if ing_id not in flagged_ingredients_by_id:
                    flagged_ingredients_by_id[ing_id] = []
                flagged_ingredients_by_id[ing_id].append({
                    "canonical_name": row["canonical_name"],
                    "regulation_code": row["regulation_code"],
                    "status": row["status"]
                })
                
    # Phase 3: Combine and rank
    response_data = []
    for rec in records:
        supplier_id = rec["supplier_id"]
        supplier_name = rec["supplier_name"]
        ingredient_ids = rec["ingredient_ids"]
        
        flagged_count = 0
        flagged_details = []
        for i_id in ingredient_ids:
            if i_id and i_id in flagged_ingredients_by_id:
                flagged_count += 1
                flagged_details.extend(flagged_ingredients_by_id[i_id])
                
        response_data.append({
            "supplier_id": supplier_id,
            "supplier_name": supplier_name,
            "flagged_ingredient_count": flagged_count,
            "flagged_details": flagged_details
        })
        
    # Sort deterministically: highest flagged count first, then alphabetically by name
    response_data.sort(key=lambda x: (-x["flagged_ingredient_count"], x["supplier_name"]))
    
    return response_data


@router.get("/suppliers/{supplier_id}/graph")
async def get_supplier_graph(request: Request, supplier_id: str):
    neo4j_driver = getattr(request.app.state, 'neo4j_driver', None)
    if not neo4j_driver:
        raise HTTPException(status_code=500, detail="Neo4j driver not initialized")
        
    # Phase 1: Neo4j structural query
    async with neo4j_driver.session() as session:
        result = await session.run("""
            MATCH (s:Supplier {pg_id: $supplier_id})<-[:SOURCED_FROM]-(c:Component)
            OPTIONAL MATCH (c)-[:USES]->(i:Ingredient)
            RETURN c.pg_id AS component_id, c.name AS component_name,
                   collect({id: i.pg_id, name: i.name, cas: i.cas_number}) AS ingredients
        """, supplier_id=supplier_id)
        records = await result.data()
        
    if not records:
        # Check if supplier even exists without components
        async with neo4j_driver.session() as session:
            s_res = await session.run("MATCH (s:Supplier {pg_id: $supplier_id}) RETURN s.name AS name", supplier_id=supplier_id)
            s_data = await s_res.data()
            if not s_data:
                raise HTTPException(status_code=404, detail="Supplier not found")
            return {"supplier_id": supplier_id, "supplier_name": s_data[0]["name"], "components": []}
            
    # Collect ingredient IDs
    all_i_ids = set()
    for rec in records:
        for i in rec["ingredients"]:
            if i.get("id"):
                all_i_ids.add(i["id"])
                
    # Phase 2: Postgres screening statuses
    ingredient_statuses = {}
    if all_i_ids:
        pool = request.app.state.pool
        async with pool.acquire() as conn:
            pg_results = await conn.fetch("""
                SELECT sr.ingredient_id, sr.status, r.code as regulation_code
                FROM screening_results sr
                JOIN regulations r ON sr.regulation_id = r.id
                WHERE sr.ingredient_id = ANY($1::uuid[])
            """, list(all_i_ids))
            
            for row in pg_results:
                ing_id = str(row["ingredient_id"])
                status = row["status"]
                reg_code = row["regulation_code"]
                
                if ing_id not in ingredient_statuses:
                    ingredient_statuses[ing_id] = []
                ingredient_statuses[ing_id].append({"status": status, "regulation_code": reg_code})
                
    # Phase 3: Build response differentiating ALLOWED, FLAGGED, UNKNOWN
    components = []
    for rec in records:
        comp_ing = []
        for i in rec["ingredients"]:
            if not i.get("id"): continue
            
            ing_id = i["id"]
            results = ingredient_statuses.get(ing_id, [])
            
            if not results:
                overall = "UNKNOWN"
            else:
                is_flagged = any(r["status"] in ('RESTRICTED', 'THRESHOLD_EXCEEDED') for r in results)
                if is_flagged:
                    overall = "FLAGGED"
                else:
                    overall = "ALLOWED"
                    
            comp_ing.append({
                "ingredient_id": ing_id,
                "name": i.get("name"),
                "cas_number": i.get("cas"),
                "overall_status": overall,
                "details": results
            })
            
        # Sort components and ingredients deterministically
        comp_ing.sort(key=lambda x: x["name"])
        components.append({
            "component_id": rec["component_id"],
            "component_name": rec["component_name"],
            "ingredients": comp_ing
        })
        
    components.sort(key=lambda x: x["component_name"])
    
    return {
        "supplier_id": supplier_id,
        "components": components
    }
