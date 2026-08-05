import os
import asyncio
import asyncpg
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

# Load environment variables securely
load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))

# Global connection pool
_pool: Optional[asyncpg.Pool] = None

async def get_db_pool() -> asyncpg.Pool:
    """Retrieve or initialize the asyncpg connection pool."""
    global _pool
    if _pool is None:
        db_url = os.environ.get("DATABASE_URL")
        if not db_url:
            raise ValueError("DATABASE_URL environment variable is not set")
        # Creating a pool instead of a single connection
        _pool = await asyncpg.create_pool(db_url, min_size=1, max_size=10)
    return _pool

async def list_applicable_regulations() -> List[str]:
    """Return the list of applicable regulations. Hardcoded for Phase 1."""
    return ["RoHS", "REACH_SVHC"]

async def get_thresholds_for_ingredient(cas_number: str, regulation_code: str) -> Dict[str, Any]:
    """
    Look up thresholds for a given CAS number and regulation code.
    This is a READ-ONLY query against the database.
    """
    pool = await get_db_pool()
    
    query = """
        SELECT 
            r.code AS regulation_code,
            i.canonical_name AS ingredient_name,
            i.cas_number,
            rt.threshold_value,
            rt.threshold_unit,
            rt.exemption_notes,
            rt.source_url
        FROM regulation_thresholds rt
        JOIN regulations r ON rt.regulation_id = r.id
        JOIN ingredients i ON rt.ingredient_id = i.id
        WHERE i.cas_number = $1 AND r.code = $2;
    """
    
    # Acquire a connection from the pool to execute the query
    async with pool.acquire() as conn:
        # fetchrow returns a Record if found, else None
        row = await conn.fetchrow(query, cas_number, regulation_code)
        
    if row:
        return dict(row)
    else:
        # Explicit structured "not found" response
        return {
            "regulation_code": regulation_code,
            "ingredient_name": None,
            "cas_number": cas_number,
            "threshold_value": None,
            "threshold_unit": None,
            "exemption_notes": None,
            "source_url": None,
            "status": "not_found"
        }
