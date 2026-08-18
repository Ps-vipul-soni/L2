import os
import sys
import uuid

import asyncpg
import json
import logging
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request

logger = logging.getLogger(__name__)

router = APIRouter()

async def get_prod_pool(request: Request):
    return request.app.state.pool

async def get_test_pool(prod_url: str) -> asyncpg.Pool:
    base_url = prod_url.rsplit('/', 1)[0]
    test_db_url = f"{base_url}/compliance_screening_test"
    return await asyncpg.create_pool(test_db_url, min_size=1, max_size=5)

def compare_sets(sets: List[set]) -> float:
    if not sets:
        return 100.0
    
    intersection = set.intersection(*sets)
    union = set.union(*sets)
    
    if not union:
        return 100.0
        
    return (len(intersection) / len(union)) * 100.0

def _get_hashable_components(components) -> set:
    return {c['name'] for c in components}

def _get_hashable_ingredients(ingredients, comp_map) -> set:
    # returns set of (component_name, canonical_name, cas_number, concentration_value, concentration_unit)
    res = set()
    for row in ingredients:
        comp_name = comp_map.get(row['component_id'], "UNKNOWN")
        val = str(row['concentration_value']) if row['concentration_value'] is not None else "None"
        res.add((comp_name, row['canonical_name'], row['cas_number'], val, row['concentration_unit']))
    return res

def _get_hashable_screening(screening, comp_map, reg_map) -> set:
    # returns set of (component_name, ingredient_id, reg_code, status)
    res = set()
    for row in screening:
        comp_name = comp_map.get(row['component_id'], "UNKNOWN")
        reg_code = reg_map.get(row['regulation_id'], "UNKNOWN")
        res.add((comp_name, str(row['ingredient_id']), reg_code, row['status']))
    return res

async def evaluate_reliability(
    document_paths: List[str], 
    n_runs: int, 
    prod_db_url: str,
    prod_pool: asyncpg.Pool
) -> Dict[str, Any]:
    
    if not 1 <= n_runs <= 5:
        raise ValueError("n_runs must be between 1 and 5")
        
    test_pool = await get_test_pool(prod_db_url)
    
    try:
        # Clean test DB
        async with test_pool.acquire() as conn:
            await conn.execute("TRUNCATE products CASCADE")
            
            # Cache regulations mapping
            regs = await conn.fetch("SELECT id, code FROM regulations")
            reg_map = {r['id']: r['code'] for r in regs}
            
        doc_results = []
        
        for doc_path in document_paths:
            print(f"Evaluating document: {doc_path}")
            

            async with test_pool.acquire() as conn:
                product_id = await conn.fetchval(
                    "INSERT INTO products (name, sku) VALUES ($1, $2) RETURNING id",
                    f"Test Product for {doc_path}",
                    f"TEST-SKU-{uuid.uuid4().hex[:8]}-{os.path.basename(doc_path)}"
                )
            
            # Setup MCPs and run N times
            from contextlib import AsyncExitStack
            from mcp import ClientSession
            from mcp.client.stdio import stdio_client, StdioServerParameters
            from backend.graph.pipeline_graph import build_pipeline_graph
            
            runs = []
            
            for i in range(n_runs):
                print(f"  Run {i+1}/{n_runs}...")
                try:
                    async with test_pool.acquire() as conn:
                        workflow_run_id = str(await conn.fetchval(
                            "INSERT INTO workflow_runs (product_id, status) VALUES ($1, 'RUNNING') RETURNING id",
                            product_id
                        ))
                        # Insert mock documents
                        doc_ids = []
                        for dpath in [doc_path]:
                            did = await conn.fetchval(
                                "INSERT INTO documents (product_id, doc_type, filename, file_path) VALUES ($1, 'SDS', $2, $3) RETURNING id",
                                product_id, os.path.basename(dpath), dpath
                            )
                            doc_ids.append(str(did))
                            await conn.execute(
                                "INSERT INTO workflow_run_documents (workflow_run_id, document_id) VALUES ($1, $2)",
                                workflow_run_id, did
                            )

                    async with AsyncExitStack() as stack:
                        mcp_script_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../mcp_servers'))
                        
                        a_params = StdioServerParameters(command=sys.executable, args=[os.path.join(mcp_script_dir, 'chemical_identity_mcp/mcp_entry.py')])
                        read_a, write_a = await stack.enter_async_context(stdio_client(a_params))
                        mcp_client_a = await stack.enter_async_context(ClientSession(read_a, write_a))
                        await mcp_client_a.initialize()
                        
                        b_params = StdioServerParameters(command=sys.executable, args=[os.path.join(mcp_script_dir, 'regulation_lookup_mcp/mcp_entry.py')])
                        read_b, write_b = await stack.enter_async_context(stdio_client(b_params))
                        mcp_client_b = await stack.enter_async_context(ClientSession(read_b, write_b))
                        await mcp_client_b.initialize()
                        
                        graph = build_pipeline_graph()
                        initial_state = {
                            "document_paths": [doc_path],
                            "workflow_run_id": workflow_run_id,
                            "product_id": product_id,
                            "db_pool": test_pool,
                            "mcp_client_a": mcp_client_a,
                            "mcp_client_b": mcp_client_b,
                            "document_ids": doc_ids
                        }
                        
                        await graph.ainvoke(initial_state)
                        
                        async with test_pool.acquire() as conn:
                            await conn.execute(
                                "UPDATE workflow_runs SET status = 'COMPLETED', completed_at = now() WHERE id = $1 AND status != 'PARTIAL'",
                                workflow_run_id
                            )
                            
                    runs.append({"status": "COMPLETED", "workflow_run_id": workflow_run_id})
                except Exception as e:
                    print(f"  Run failed: {e}")
                    runs.append({"status": "FAILED", "error": str(e), "workflow_run_id": workflow_run_id})
                    async with test_pool.acquire() as conn:
                        await conn.execute("UPDATE workflow_runs SET status = 'FAILED' WHERE id = $1", workflow_run_id)

            
            # Compare runs
            components_sets = []
            ingredients_sets = []
            screening_sets = []
            decision_status_list = []
            risk_score_list = []
            
            for i, run in enumerate(runs):
                status = run.get('status') if isinstance(run, dict) else run.overall_status
                if status == "FAILED":
                    components_sets.append(set())
                    ingredients_sets.append(set())
                    screening_sets.append(set())
                    decision_status_list.append("FAILED")
                    risk_score_list.append(None)
                    continue
                
                workflow_run_id = run.get('workflow_run_id') if isinstance(run, dict) else run.workflow_run_id
                
                async with test_pool.acquire() as conn:
                    components = await conn.fetch("SELECT id, name FROM components WHERE product_id = $1", product_id)
                    comp_map = {c['id']: c['name'] for c in components}
                    components_sets.append(_get_hashable_components(components))
                    
                    if not comp_map:
                        ingredients_sets.append(set())
                        screening_sets.append(set())
                        decision_status_list.append(status)
                        risk_score_list.append(None)
                        continue
                        
                    ingredients = await conn.fetch("""
                        SELECT ci.component_id, i.canonical_name, i.cas_number, ci.concentration_value, ci.concentration_unit
                        FROM component_ingredients ci
                        JOIN ingredients i ON ci.ingredient_id = i.id
                        WHERE ci.component_id = ANY($1::uuid[])
                    """, list(comp_map.keys()))
                    ingredients_sets.append(_get_hashable_ingredients(ingredients, comp_map))
                    
                    screening = await conn.fetch("""
                        SELECT component_id, ingredient_id, regulation_id, status
                        FROM screening_results
                        WHERE workflow_run_id = $1
                    """, workflow_run_id)
                    screening_sets.append(_get_hashable_screening(screening, comp_map, reg_map))
                    
                    decision = await conn.fetchrow("SELECT overall_status, risk_score FROM compliance_decisions WHERE workflow_run_id = $1", workflow_run_id)
                    if decision:
                        decision_status_list.append(decision['overall_status'])
                        risk_score_list.append(float(decision['risk_score']) if decision['risk_score'] is not None else None)
                    else:
                        decision_status_list.append("NO_DECISION")
                        risk_score_list.append(None)

            comp_score = compare_sets(components_sets)
            ing_score = compare_sets(ingredients_sets)
            scr_score = compare_sets(screening_sets)
            
            data_consistency = (comp_score + ing_score + scr_score) / 3.0
            
            first_status = decision_status_list[0] if decision_status_list else "FAILED"
            decision_match = all(s == first_status for s in decision_status_list)
            decision_consistency = 100.0 if decision_match else 0.0
            
            mismatches = {}
            if len(set(decision_status_list)) > 1:
                mismatches['decision_status'] = decision_status_list
            
            valid_scores = [s for s in risk_score_list if s is not None]
            if valid_scores and (max(valid_scores) - min(valid_scores) > 0.01):
                mismatches['risk_score'] = risk_score_list
                
            if comp_score < 100.0: mismatches['components'] = [list(s) for s in components_sets]
            if ing_score < 100.0: mismatches['ingredients'] = [list(s) for s in ingredients_sets]
            if scr_score < 100.0: mismatches['screening'] = [list(s) for s in screening_sets]
            
            doc_results.append({
                "document_id": doc_path,
                "runs_completed": len([s for s in decision_status_list if s != "FAILED"]),
                "runs_failed": len([s for s in decision_status_list if s == "FAILED"]),
                "decision_consistency_score": decision_consistency,
                "data_consistency_score": data_consistency,
                "per_field_scores": {
                    "components": comp_score,
                    "ingredients": ing_score,
                    "screening": scr_score
                },
                "mismatches": mismatches
            })
            
        overall_data_consistency = sum(r['data_consistency_score'] for r in doc_results) / len(doc_results) if doc_results else 0.0
        overall_decision_consistency = sum(r['decision_consistency_score'] for r in doc_results) / len(doc_results) if doc_results else 0.0
        
        async with prod_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO reliability_evaluations 
                (document_paths, n_runs, overall_consistency_score, decision_consistency_score, data_consistency_score, per_field_scores, mismatches)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """, 
                json.dumps(document_paths),
                n_runs,
                (overall_data_consistency + overall_decision_consistency) / 2.0,
                overall_decision_consistency,
                overall_data_consistency,
                json.dumps({r['document_id']: r['per_field_scores'] for r in doc_results}),
                json.dumps({r['document_id']: r['mismatches'] for r in doc_results})
            )
            
        return {
            "evaluated_documents": document_paths,
            "n_runs": n_runs,
            "overall_decision_consistency": overall_decision_consistency,
            "overall_data_consistency": overall_data_consistency,
            "document_results": doc_results
        }
    finally:
        await test_pool.close()

@router.post("/run")
async def trigger_reliability_eval(
    payload: dict,
    prod_pool: asyncpg.Pool = Depends(get_prod_pool)
):

    prod_url = os.environ.get("DATABASE_URL")
    docs = payload.get("document_paths", [])
    n_runs = payload.get("n_runs", 3)
    
    if not docs:
        raise HTTPException(status_code=400, detail="Must provide document_paths")
        
    try:
        res = await evaluate_reliability(docs, n_runs, prod_url, prod_pool)
        return res
    except Exception as e:
        logger.error(f"Reliability eval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
