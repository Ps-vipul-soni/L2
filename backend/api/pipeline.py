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

@router.get("/review-queue")
async def get_review_queue(request: Request):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        queue = await conn.fetch(
            """
            SELECT rq.id, rq.document_id, d.filename, rq.screening_result_id, rq.reason
            FROM review_queue rq
            JOIN documents d ON rq.document_id = d.id
            WHERE rq.status = 'OPEN'
            """
        )
        # Convert UUIDs to strings and map to dicts
        results = [dict(q) for q in queue]
        for r in results:
            r["id"] = str(r["id"])
            r["document_id"] = str(r["document_id"])
            if r["screening_result_id"]:
                r["screening_result_id"] = str(r["screening_result_id"])
            
        return results
