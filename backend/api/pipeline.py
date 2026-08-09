import os
import sys
import uuid
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from contextlib import AsyncExitStack
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

from backend.graph.pipeline_graph import build_pipeline_graph

router = APIRouter()

class TriggerRequest(BaseModel):
    document_id: str

@router.post("/trigger")
async def trigger_pipeline(request: Request, body: TriggerRequest):
    document_id = body.document_id
    try:
        uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document_id format.")
        
    pool = request.app.state.pool
    
    # Check if document exists and get path/product
    async with pool.acquire() as conn:
        doc = await conn.fetchrow("SELECT file_path, product_id FROM documents WHERE id = $1", document_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
            
        file_path = doc["file_path"]
        product_id = str(doc["product_id"])
        
        if not os.path.exists(file_path):
            raise HTTPException(status_code=500, detail="Document file is missing from disk")
            
        # Create workflow run
        workflow_run_id = str(await conn.fetchval(
            "INSERT INTO workflow_runs (product_id, status) VALUES ($1, 'RUNNING') RETURNING id",
            product_id
        ))
        
    # Run the pipeline synchronously (blocking the request)
    # MCP server initialization
    async with AsyncExitStack() as stack:
        try:
            mcp_script_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../mcp_servers'))
            
            # Setup Agent A
            a_params = StdioServerParameters(command=sys.executable, args=[os.path.join(mcp_script_dir, 'chemical_identity_mcp/mcp_entry.py')])
            read_a, write_a = await stack.enter_async_context(stdio_client(a_params))
            mcp_client_a = await stack.enter_async_context(ClientSession(read_a, write_a))
            await mcp_client_a.initialize()
            
            # Setup Agent B
            b_params = StdioServerParameters(command=sys.executable, args=[os.path.join(mcp_script_dir, 'regulation_lookup_mcp/mcp_entry.py')])
            read_b, write_b = await stack.enter_async_context(stdio_client(b_params))
            mcp_client_b = await stack.enter_async_context(ClientSession(read_b, write_b))
            await mcp_client_b.initialize()
            
        except Exception as e:
            # Mark as failed if MCP fails
            async with pool.acquire() as conn:
                await conn.execute("UPDATE workflow_runs SET status = 'FAILED' WHERE id = $1", workflow_run_id)
            raise HTTPException(status_code=500, detail=f"Failed to start MCP servers: {str(e)}")
            
        # Invoke Graph
        try:
            graph = build_pipeline_graph()
            initial_state = {
                "document_path": file_path,
                "workflow_run_id": workflow_run_id,
                "product_id": product_id,
                "db_pool": pool,
                "mcp_client_a": mcp_client_a,
                "mcp_client_b": mcp_client_b,
                "document_id": document_id
            }
            
            # Wait for LangGraph to complete
            await graph.ainvoke(initial_state)
            
            # Graceful cleanup - Update to COMPLETED if not already PARTIAL
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE workflow_runs SET status = 'COMPLETED', completed_at = now() WHERE id = $1 AND status != 'PARTIAL'",
                    workflow_run_id
                )
        except Exception as e:
            async with pool.acquire() as conn:
                await conn.execute("UPDATE workflow_runs SET status = 'FAILED', completed_at = now() WHERE id = $1", workflow_run_id)
            raise HTTPException(status_code=500, detail=f"Pipeline execution failed: {str(e)}")
            
    return {"workflow_run_id": workflow_run_id, "status": "Pipeline completed or halted for review."}

@router.get("/status/{workflow_run_id}")
async def get_status(request: Request, workflow_run_id: str):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        run = await conn.fetchrow("SELECT status, started_at, completed_at FROM workflow_runs WHERE id = $1", workflow_run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Workflow run not found")
            
        response = dict(run)
        if run["status"] == "COMPLETED":
            report = await conn.fetchrow("SELECT executive_summary FROM reports WHERE workflow_run_id = $1", workflow_run_id)
            if report:
                response["report"] = report["executive_summary"]
                
        return response

@router.get("/workflow-runs/{workflow_run_id}/summary")
async def get_workflow_summary(request: Request, workflow_run_id: str):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        run = await conn.fetchrow("SELECT status FROM workflow_runs WHERE id = $1", workflow_run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Workflow run not found")

        decision = await conn.fetchrow("SELECT overall_status FROM compliance_decisions WHERE workflow_run_id = $1", workflow_run_id)
        overall_status = decision["overall_status"] if decision else None

        screening_count = await conn.fetchval("SELECT count(*) FROM screening_results WHERE workflow_run_id = $1", workflow_run_id)
        report_count = await conn.fetchval("SELECT count(*) FROM reports WHERE workflow_run_id = $1", workflow_run_id)

        inferred_stages = {
            "Document Understanding": True if screening_count > 0 else "Unknown",
            "Regulation Planning": True if screening_count > 0 else "Unknown",
            "Compliance Screening": True if screening_count > 0 else False,
            "Report Generation": True if report_count > 0 else False
        }

        reasons = []
        if run["status"] == "PARTIAL":
            queue_items = await conn.fetch("""
                SELECT rq.reason 
                FROM review_queue rq
                JOIN screening_results sr ON rq.screening_result_id = sr.id
                WHERE sr.workflow_run_id = $1 AND rq.status = 'OPEN'
            """, workflow_run_id)
            reasons = [item["reason"] for item in queue_items]

        return {
            "status": run["status"],
            "overall_status": overall_status,
            "inferred_stages": inferred_stages,
            "review_queue_reasons": reasons
        }

@router.get("/review-queue")
async def get_review_queue(request: Request, status: str = "OPEN", review_type: str = "ALL"):
    if status not in ("OPEN", "RESOLVED", "ALL"):
        raise HTTPException(status_code=400, detail="Invalid status parameter")
    if review_type not in ("EXTRACTION", "SCREENING", "ALL"):
        raise HTTPException(status_code=400, detail="Invalid review_type parameter")

    pool = request.app.state.pool
    async with pool.acquire() as conn:
        query = """
            SELECT 
                rq.id, 
                rq.document_id, 
                d.filename, 
                rq.screening_result_id, 
                rq.reason, 
                rq.status,
                rq.created_at,
                sr.workflow_run_id,
                p.name AS product_name,
                i.canonical_name AS ingredient_name
            FROM review_queue rq
            LEFT JOIN documents d ON rq.document_id = d.id
            LEFT JOIN screening_results sr ON rq.screening_result_id = sr.id
            LEFT JOIN workflow_runs w ON sr.workflow_run_id = w.id
            LEFT JOIN products p ON w.product_id = p.id
            LEFT JOIN ingredients i ON sr.ingredient_id = i.id
            WHERE 1=1
        """
        args = []

        if status != "ALL":
            args.append(status)
            query += f" AND rq.status = ${len(args)}"

        if review_type == "EXTRACTION":
            args.append("%extraction%")
            query += f" AND rq.reason ILIKE ${len(args)}"
        elif review_type == "SCREENING":
            args.append("%screening%")
            query += f" AND rq.reason ILIKE ${len(args)}"

        query += " ORDER BY rq.created_at ASC, rq.id ASC"

        queue = await conn.fetch(query, *args)
        
        # Convert UUIDs and Datetimes to strings and map to dicts
        results = [dict(q) for q in queue]
        for r in results:
            r["id"] = str(r["id"])
            r["document_id"] = str(r["document_id"]) if r["document_id"] else None
            r["screening_result_id"] = str(r["screening_result_id"]) if r["screening_result_id"] else None
            r["workflow_run_id"] = str(r["workflow_run_id"]) if r["workflow_run_id"] else None
            r["created_at"] = r["created_at"].isoformat() if r["created_at"] else None
            
        return results

@router.post("/review-queue/{review_id}/resolve")
async def resolve_review_item(request: Request, review_id: str):
    try:
        uuid.UUID(review_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid review_id format.")
        
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT status FROM review_queue WHERE id = $1", review_id)
        if not row:
            raise HTTPException(status_code=404, detail="Review item not found")
            
        if row["status"] in ("RESOLVED", "DISMISSED"):
            raise HTTPException(status_code=409, detail=f"Review item is already {row['status']}")
            
        # This endpoint only records manual review completion and does NOT complete the workflow.
        # Do NOT modify workflow_runs.status here.
        updated = await conn.execute(
            """
            UPDATE review_queue 
            SET status = 'RESOLVED', resolved_at = now() 
            WHERE id = $1 AND status = 'OPEN'
            """, 
            review_id
        )
        
        if updated == "UPDATE 0":
            raise HTTPException(status_code=409, detail="Failed to resolve due to concurrent modification.")
            
    return {"status": "success", "message": "Item marked as manually reviewed"}
from backend.utils.matching import check_string_match, check_jurisdiction

@router.get("/{workflow_run_id}/stages")
async def get_pipeline_stages(request: Request, workflow_run_id: str):
    pool = request.app.state.pool
    
    try:
        uuid.UUID(workflow_run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid workflow_run_id format.")
        
    async with pool.acquire() as conn:
        # Check run exists
        run = await conn.fetchrow("SELECT product_id, status FROM workflow_runs WHERE id = $1", workflow_run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Workflow run not found")
            
        product_id = run["product_id"]
        
        # 1. Document Understanding
        doc = await conn.fetchrow("""
            SELECT d.filename, d.doc_type, d.extraction_confidence, d.extraction_notes, d.id
            FROM documents d
            WHERE d.product_id = $1
            ORDER BY d.uploaded_at DESC LIMIT 1
        """, product_id)
        
        doc_understanding = None
        doc_id = None
        if doc:
            doc_id = doc["id"]
            doc_understanding = {
                "filename": doc["filename"],
                "doc_type": doc["doc_type"],
                "extraction_confidence": float(doc["extraction_confidence"]) if doc["extraction_confidence"] else None,
                "extraction_notes": doc["extraction_notes"]
            }
            
        # 2. Ingredient Extraction
        ingredient_extraction = []
        if doc_id:
            ingredients = await conn.fetch("""
                SELECT 
                    c.name as component_name,
                    i.canonical_name,
                    i.cas_number,
                    ci.concentration_value,
                    ci.concentration_unit,
                    i.id as ingredient_id
                FROM component_ingredients ci
                JOIN components c ON ci.component_id = c.id
                JOIN ingredients i ON ci.ingredient_id = i.id
                WHERE ci.source_document_id = $1
                ORDER BY c.name ASC, i.canonical_name ASC
            """, doc_id)
            for ing in ingredients:
                ingredient_extraction.append({
                    "component_name": ing["component_name"],
                    "canonical_name": ing["canonical_name"],
                    "cas_number": ing["cas_number"],
                    "concentration_value": float(ing["concentration_value"]) if ing["concentration_value"] else None,
                    "concentration_unit": ing["concentration_unit"],
                    "ingredient_id": ing["ingredient_id"]
                })
                
        # 3. Chemical Normalization
        chemical_normalization = []
        if ingredient_extraction:
            ing_ids = list(set([i["ingredient_id"] for i in ingredient_extraction]))
            
            # Fetch aliases for all extracted ingredients
            aliases_records = await conn.fetch("""
                SELECT ingredient_id, raw_name
                FROM ingredient_synonyms
                WHERE ingredient_id = ANY($1::uuid[])
                ORDER BY raw_name ASC
            """, ing_ids)
            
            aliases_map = {}
            for rec in aliases_records:
                aliases_map.setdefault(rec["ingredient_id"], []).append(rec["raw_name"])
                
            seen_chem = set()
            for ing in ingredient_extraction:
                if ing["ingredient_id"] not in seen_chem:
                    seen_chem.add(ing["ingredient_id"])
                    
                    # Optional: get pubchem_cid if it existed in schema, but it doesn't currently.
                    # Fallback to None if not in table, wait, checking schema:
                    # ingredients has canonical_name, cas_number.
                    
                    chemical_normalization.append({
                        "canonical_name": ing["canonical_name"],
                        "cas_number": ing["cas_number"],
                        "aliases": aliases_map.get(ing["ingredient_id"], [])
                    })
                    
            # Ensure deterministic order
            chemical_normalization.sort(key=lambda x: x["canonical_name"])

        # 4. Regulation Planning
        regulation_planning = []
        product = await conn.fetchrow("SELECT product_type, market_country, customer_name FROM products WHERE id = $1", product_id)
        
        regs = await conn.fetch("SELECT code, jurisdiction, applies_to_product_types, customer_name FROM regulations ORDER BY code ASC")
        
        for reg in regs:
            code = reg['code']
            r_juris = reg['jurisdiction']
            r_types = reg['applies_to_product_types']
            r_cust = reg['customer_name']
            
            applies = False
            reasons = []
            
            # 1. Customer Check
            if r_cust and r_cust != product['customer_name']:
                reasons.append(f"Customer mismatch (Regulation targets {r_cust})")
            else:
                if r_cust:
                    reasons.append(f"Customer match ({r_cust})")
                
                # 2. Jurisdiction Check
                if not check_jurisdiction(product['market_country'], r_juris):
                    reasons.append(f"Jurisdiction mismatch (Market is {product['market_country']}, regulation requires {r_juris})")
                else:
                    if r_juris == 'Global':
                        reasons.append("Global jurisdiction applies")
                    else:
                        reasons.append(f"Jurisdiction match ({r_juris})")
                    
                    # 3. Product Type Check
                    if not r_types:
                        applies = True
                        reasons.append("Applies to any product type")
                    else:
                        if check_string_match(product['product_type'], r_types):
                            applies = True
                            reasons.append(f"Product type match ({product['product_type']})")
                        else:
                            reasons.append(f"Product type mismatch (Is {product['product_type']}, requires one of {r_types})")
                            
            regulation_planning.append({
                "regulation_code": code,
                "applies": applies,
                "reason": ", ".join(reasons)
            })

    return {
        "document_understanding": doc_understanding,
        "ingredient_extraction": [{k: v for k, v in i.items() if k != "ingredient_id"} for i in ingredient_extraction],
        "chemical_normalization": chemical_normalization,
        "regulation_planning": regulation_planning
    }
