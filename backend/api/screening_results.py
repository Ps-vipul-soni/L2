from fastapi import APIRouter, Request, HTTPException
from typing import Optional

router = APIRouter(tags=["Screening Results"])

@router.get("/regulations")
async def get_regulations(request: Request):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        records = await conn.fetch("""
            SELECT 
                r.id, 
                r.code, 
                r.name, 
                COUNT(DISTINCT rt.ingredient_id) as chemical_count 
            FROM regulations r
            LEFT JOIN regulation_thresholds rt ON r.id = rt.regulation_id
            GROUP BY r.id, r.code, r.name
            ORDER BY r.code ASC
        """)
    return [{"id": str(r["id"]), "code": r["code"], "name": r["name"], "chemical_count": r["chemical_count"]} for r in records]

@router.get("/screening-results")
async def get_screening_results(
    request: Request,
    product_id: Optional[str] = None,
    regulation_code: Optional[str] = None,
    status: Optional[str] = None,
    ingredient: Optional[str] = None
):
    valid_statuses = {'RESTRICTED', 'ALLOWED', 'THRESHOLD_EXCEEDED', 'EXEMPTION_AVAILABLE', 'NEEDS_REVIEW'}
    
    if status and status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")
        
    pool = request.app.state.pool
    
    query = """
        SELECT 
            p.name as product_name,
            c.name as component_name,
            i.canonical_name,
            i.cas_number,
            r.code as regulation_code,
            s.status,
            s.measured_value,
            s.threshold_value,
            s.confidence,
            s.reasoning,
            s.workflow_run_id,
            s.created_at
        FROM screening_results s
        JOIN workflow_runs w ON s.workflow_run_id = w.id
        JOIN products p ON w.product_id = p.id
        JOIN components c ON s.component_id = c.id
        JOIN ingredients i ON s.ingredient_id = i.id
        JOIN regulations r ON s.regulation_id = r.id
        WHERE 1=1
    """
    
    args = []
    
    if product_id:
        args.append(product_id)
        query += f" AND w.product_id = ${len(args)}"
        
    if regulation_code:
        args.append(regulation_code)
        query += f" AND r.code = ${len(args)}"
        
    if status:
        args.append(status)
        query += f" AND s.status = ${len(args)}"
        
    if ingredient:
        args.append(f"%{ingredient}%")
        query += f" AND (i.canonical_name ILIKE ${len(args)} OR i.cas_number ILIKE ${len(args)})"
        
    query += " ORDER BY s.created_at DESC, s.id ASC LIMIT 501"
    
    async with pool.acquire() as conn:
        records = await conn.fetch(query, *args)
        
    truncated = False
    if len(records) == 501:
        truncated = True
        records = records[:500]
        
    results = []
    for r in records:
        results.append({
            "product_name": r["product_name"],
            "component_name": r["component_name"],
            "canonical_name": r["canonical_name"],
            "cas_number": r["cas_number"],
            "regulation_code": r["regulation_code"],
            "status": r["status"],
            "measured_value": float(r["measured_value"]) if r["measured_value"] is not None else None,
            "threshold_value": float(r["threshold_value"]) if r["threshold_value"] is not None else None,
            "confidence": float(r["confidence"]) if r["confidence"] is not None else None,
            "reasoning": r["reasoning"],
            "workflow_run_id": str(r["workflow_run_id"]),
            "created_at": r["created_at"].isoformat() if r["created_at"] else None
        })
        
    return {
        "results": results,
        "truncated": truncated
    }
