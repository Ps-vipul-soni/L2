import logging
import asyncpg
from typing import Optional
import asyncio

logger = logging.getLogger(__name__)

_background_tasks = set()

async def log_tool_call(
    pool: asyncpg.Pool, 
    workflow_run_id: Optional[str], 
    category: str, 
    status: str
):
    """
    Non-blocking telemetry logger for tool calls.
    Fails safely without throwing exceptions into the caller's pipeline.
    """
    try:
        if not workflow_run_id:
            logger.warning(f"Telemetry missing workflow_run_id for {category} ({status})")
            return
            
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO tool_call_logs (workflow_run_id, category, status) VALUES ($1::uuid, $2, $3)",
                workflow_run_id, category, status
            )
    except Exception as e:
        logger.error(f"Failed to log telemetry: {e}")

def fire_and_forget_log(pool, workflow_run_id, category, status):
    task = asyncio.create_task(log_tool_call(pool, workflow_run_id, category, status))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
