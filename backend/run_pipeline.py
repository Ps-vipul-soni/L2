import asyncio
import os
import sys
import argparse
from contextlib import AsyncExitStack
import asyncpg
from dotenv import load_dotenv

from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

# Add root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.graph.pipeline_graph import build_pipeline_graph

load_dotenv(os.path.join(os.path.dirname(__file__), '../.env'))

async def get_db_pool() -> asyncpg.Pool:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL environment variable is not set")
    return await asyncpg.create_pool(db_url, min_size=1, max_size=5)

async def run_pipeline(document_path: str):
    print(f"Starting pipeline for: {document_path}")
    
    # 1. MCP Server Orchestration (Fail Fast)
    # Using AsyncExitStack to cleanly manage multiple async context managers
    async with AsyncExitStack() as stack:
        try:
            print("Connecting to Chemical Identity MCP Server (Agent A)...")
            server_a_params = StdioServerParameters(
                command=sys.executable,
                args=[os.path.abspath(os.path.join(os.path.dirname(__file__), '../mcp_servers/chemical_identity_mcp/mcp_entry.py'))]
            )
            read_a, write_a = await stack.enter_async_context(stdio_client(server_a_params))
            mcp_client_a = await stack.enter_async_context(ClientSession(read_a, write_a))
            await mcp_client_a.initialize()
            
            print("Connecting to Regulation Lookup MCP Server (Agent B)...")
            server_b_params = StdioServerParameters(
                command=sys.executable,
                args=[os.path.abspath(os.path.join(os.path.dirname(__file__), '../mcp_servers/regulation_lookup_mcp/mcp_entry.py'))]
            )
            read_b, write_b = await stack.enter_async_context(stdio_client(server_b_params))
            mcp_client_b = await stack.enter_async_context(ClientSession(read_b, write_b))
            await mcp_client_b.initialize()
            
            print("MCP Servers connected successfully.")
            
        except Exception as e:
            print(f"\n[ERROR] Failed to start/connect to MCP Servers: {e}")
            print("Cleaning up and failing fast.")
            sys.exit(1)
            
        # 2. Database & Placeholder Setup
        pool = await get_db_pool()
        
        async with pool.acquire() as conn:
            # Check for existing product, else create placeholder
            product_row = await conn.fetchrow("SELECT id FROM products LIMIT 1")
            if product_row:
                product_id = str(product_row["id"])
            else:
                product_id = str(await conn.fetchval(
                    "INSERT INTO products (name, sku, product_type) VALUES ($1, $2, $3) RETURNING id",
                    "Placeholder Product", "SKU-000", "electronics"
                ))
                print(f"No product specified. Created placeholder product: product_id={product_id}")
            
            # Create documents row
            ext = os.path.splitext(document_path)[1].lower()
            doc_type = "SDS"
            if ext in [".csv", ".xlsx", ".xls"]:
                doc_type = "BOM"
            elif ext == ".xml":
                doc_type = "FMD"
                
            document_id = str(await conn.fetchval(
                """
                INSERT INTO documents (product_id, doc_type, filename, file_path)
                VALUES ($1, $2, $3, $4) RETURNING id
                """,
                product_id, doc_type, os.path.basename(document_path), os.path.abspath(document_path)
            ))
            print(f"Created documents row: {document_id}")
            
            # Create workflow_runs row with RUNNING status
            workflow_run_id = str(await conn.fetchval(
                "INSERT INTO workflow_runs (product_id, status) VALUES ($1, 'RUNNING') RETURNING id",
                product_id
            ))
            print(f"Started workflow run: {workflow_run_id}")
            
        # 3. LangGraph Execution
        try:
            graph = build_pipeline_graph()
            
            # Initial state
            initial_state = {
                "document_path": os.path.abspath(document_path),
                "workflow_run_id": workflow_run_id,
                "product_id": product_id,
                "db_pool": pool,
                "mcp_client_a": mcp_client_a,
                "mcp_client_b": mcp_client_b,
                
                "document_id": document_id,
                "extraction_result": None,
                "normalization_result": None,
                "screening_result": None,
                "decision_result": None,
                "report_result": None
            }
            
            print("\nInvoking LangGraph Pipeline...")
            final_state = await graph.ainvoke(initial_state)
            
            # 4. Graceful DB Cleanup on Success
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE workflow_runs SET status = 'COMPLETED', completed_at = now() WHERE id = $1 AND status != 'PARTIAL'",
                    workflow_run_id
                )
            print(f"\nWorkflow {workflow_run_id} COMPLETED successfully.")
            
        except Exception as e:
            # Graceful DB Cleanup on Failure
            print(f"\n[ERROR] Pipeline crashed mid-run: {type(e).__name__} - {e}")
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE workflow_runs SET status = 'FAILED', completed_at = now() WHERE id = $1",
                    workflow_run_id
                )
            print(f"Workflow {workflow_run_id} marked as FAILED.")
            sys.exit(1)
        finally:
            await pool.close()
            
    # Context manager exits here, safely terminating Stdio MCP subprocesses
    print("MCP subprocesses cleaned up successfully.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Compliance Screening Pipeline")
    parser.add_argument("document_path", help="Path to the document file (SDS, BOM, FMD)")
    args = parser.parse_args()
    
    if not os.path.exists(args.document_path):
        print(f"File not found: {args.document_path}")
        sys.exit(1)
        
    asyncio.run(run_pipeline(args.document_path))
