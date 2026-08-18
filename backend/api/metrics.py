from fastapi import APIRouter, Depends, HTTPException, Query, Request
import asyncpg

import json

router = APIRouter(prefix="/metrics", tags=["Metrics"])

async def get_db_pool(request: Request):
    return request.app.state.pool

@router.get("/task_success_rate")
async def get_task_success_rate(
    request: Request,
    time_window: str = Query("24h", description="Time window: 24h, 7d, 30d, all"),
    pool: asyncpg.Pool = Depends(get_db_pool)
):
    """
    Calculates the Task Success Rate for workflow runs.
    
    Definition:
    - Successful workflows: COMPLETED
    - Eligible workflows: COMPLETED, FAILED, PARTIAL
    - Excluded workflows: RUNNING (incomplete)
    
    PARTIAL workflows are treated as eligible but unsuccessful because they represent
    cases where the automation could not confidently complete the task and had to halt
    for human intervention. Therefore, they count against the automated task success rate.
    """
    
    # 1. Determine time filter string for SQL
    # We use started_at because completed_at is NULL for PARTIAL runs (as found in Prompt 1 audit).
    # Thus, started_at is the most reliable timestamp for all eligible runs.
    time_filter = ""
    if time_window == "24h":
        time_filter = "AND started_at >= NOW() - INTERVAL '24 hours'"
    elif time_window == "7d":
        time_filter = "AND started_at >= NOW() - INTERVAL '7 days'"
    elif time_window == "30d":
        time_filter = "AND started_at >= NOW() - INTERVAL '30 days'"
    elif time_window == "all":
        time_filter = ""
    else:
        raise HTTPException(status_code=400, detail="Invalid time_window. Use 24h, 7d, 30d, or all.")
        
    query = f"""
        SELECT 
            COUNT(*) FILTER (WHERE status = 'COMPLETED') as successful_count,
            COUNT(*) FILTER (WHERE status IN ('COMPLETED', 'FAILED', 'PARTIAL')) as eligible_count
        FROM workflow_runs
        WHERE status IN ('COMPLETED', 'FAILED', 'PARTIAL')
        {time_filter}
    """
    
    async with pool.acquire() as conn:
        result = await conn.fetchrow(query)
        
    successful_count = result["successful_count"]
    eligible_count = result["eligible_count"]
    
    if eligible_count == 0:
        return {
            "task_success_rate": "NO ELIGIBLE DATA",
            "successful_count": 0,
            "eligible_count": 0,
            "message": "Insufficient or no eligible data in this time window."
        }
        
    rate = (successful_count / eligible_count) * 100.0
    return {
        "task_success_rate": round(rate, 2),
        "successful_count": successful_count,
        "eligible_count": eligible_count
    }

@router.get("/tool_call_success_rate")
async def get_tool_call_success_rate(
    request: Request,
    time_window: str = Query("24h", description="Time window: 24h, 7d, 30d, all"),
    pool: asyncpg.Pool = Depends(get_db_pool)
):
    """
    Calculates the Tool Call Success Rate for AI interactions (LLM and MCP).
    DB operations are explicitly excluded.
    """
    time_filter = ""
    if time_window == "24h":
        time_filter = "WHERE created_at >= NOW() - INTERVAL '24 hours'"
    elif time_window == "7d":
        time_filter = "WHERE created_at >= NOW() - INTERVAL '7 days'"
    elif time_window == "30d":
        time_filter = "WHERE created_at >= NOW() - INTERVAL '30 days'"
    elif time_window == "all":
        time_filter = ""
    else:
        raise HTTPException(status_code=400, detail="Invalid time_window. Use 24h, 7d, 30d, or all.")
        
    query = f"""
        SELECT 
            category,
            COUNT(*) as total_calls,
            COUNT(*) FILTER (WHERE status = 'SUCCESS') as successful_calls
        FROM tool_call_logs
        {time_filter}
        GROUP BY category
    """
    
    async with pool.acquire() as conn:
        rows = await conn.fetch(query)
        
    results = {
        "overall_rate": "N/A",
        "total_calls": 0,
        "successful_calls": 0,
        "failed_calls": 0,
        "categories": {
            "LLM": {"total_calls": 0, "successful_calls": 0, "failed_calls": 0, "rate": "N/A"},
            "MCP": {"total_calls": 0, "successful_calls": 0, "failed_calls": 0, "rate": "N/A"}
        }
    }
    
    total_all = 0
    success_all = 0
    
    for row in rows:
        cat = row["category"]
        total = row["total_calls"]
        success = row["successful_calls"]
        failed = total - success
        
        # Only process known categories
        if cat in results["categories"]:
            results["categories"][cat] = {
                "total_calls": total,
                "successful_calls": success,
                "failed_calls": failed,
                "rate": round((success / total) * 100.0, 2) if total > 0 else "N/A"
            }
            total_all += total
            success_all += success
            
    results["total_calls"] = total_all
    results["successful_calls"] = success_all
    results["failed_calls"] = total_all - success_all
    
    if total_all > 0:
        results["overall_rate"] = round((success_all / total_all) * 100.0, 2)
        
    return results

@router.get("/graceful_failure_rate")
async def get_graceful_failure_rate(
    request: Request,
    time_window: str = Query("24h", description="Time window: 24h, 7d, 30d, all"),
    pool: asyncpg.Pool = Depends(get_db_pool)
):
    """
    Calculates the Graceful Failure Handling Rate.
    Formula: failures safely routed to review (PARTIAL) / non-recoverable failures (PARTIAL + FAILED) * 100
    """
    time_filter = ""
    if time_window == "24h":
        time_filter = "AND started_at >= NOW() - INTERVAL '24 hours'"
    elif time_window == "7d":
        time_filter = "AND started_at >= NOW() - INTERVAL '7 days'"
    elif time_window == "30d":
        time_filter = "AND started_at >= NOW() - INTERVAL '30 days'"
    elif time_window == "all":
        time_filter = ""
    else:
        raise HTTPException(status_code=400, detail="Invalid time_window. Use 24h, 7d, 30d, or all.")
        
    query = f"""
        SELECT 
            COUNT(*) FILTER (WHERE status = 'PARTIAL') as routed_count,
            COUNT(*) as total_failures_count
        FROM workflow_runs
        WHERE status IN ('PARTIAL', 'FAILED')
        {time_filter}
    """
    
    async with pool.acquire() as conn:
        result = await conn.fetchrow(query)
        
    routed = result["routed_count"] or 0
    total = result["total_failures_count"] or 0
    
    if total == 0:
        return {
            "graceful_failure_rate": "N/A",
            "routed_count": 0,
            "total_failures_count": 0,
            "message": "No non-recoverable failures in this time window."
        }
        
    rate = (routed / total) * 100.0
    return {
        "graceful_failure_rate": round(rate, 2),
        "routed_count": routed,
        "total_failures_count": total
    }

@router.get("/reliability_latest")
async def get_reliability_latest(
    request: Request,
    pool: asyncpg.Pool = Depends(get_db_pool)
):
    """
    Fetches the latest reliability evaluation result.
    """
    query = """
        SELECT *
        FROM reliability_evaluations
        ORDER BY evaluated_at DESC
        LIMIT 1
    """
    
    async with pool.acquire() as conn:
        try:
            result = await conn.fetchrow(query)
            if not result:
                return {"status": "NO_DATA"}
                
            return {
                "status": "SUCCESS",
                "overall_consistency_score": float(result["overall_consistency_score"]),
                "decision_consistency_score": float(result["decision_consistency_score"]),
                "data_consistency_score": float(result["data_consistency_score"]),
                "n_runs": result["n_runs"],
                "document_paths": json.loads(result["document_paths"]) if isinstance(result["document_paths"], str) else result["document_paths"],
                "evaluated_at": result["evaluated_at"].isoformat() if result["evaluated_at"] else None
            }
        except Exception as e:
            # Table might not exist if migration hasn't run, etc.
            return {"status": "ERROR", "detail": str(e)}
