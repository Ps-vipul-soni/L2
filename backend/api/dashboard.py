from fastapi import APIRouter, Request

router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"]
)

@router.get("/summary")
async def get_dashboard_summary(request: Request):
    pool = request.app.state.pool
    
    async with pool.acquire() as conn:
        # 1. products_screened_count
        products_screened = await conn.fetchval(
            "SELECT COUNT(DISTINCT product_id) FROM workflow_runs"
        )
        
        # 2. ingredients_identified_count
        ingredients_identified = await conn.fetchval("""
            SELECT COUNT(DISTINCT ci.ingredient_id) 
            FROM component_ingredients ci 
            JOIN components c ON ci.component_id = c.id 
            WHERE c.product_id IN (SELECT product_id FROM workflow_runs)
        """)
        
        # 3. regulations_evaluated_count
        regulations_evaluated = await conn.fetchval(
            "SELECT COUNT(DISTINCT regulation_id) FROM screening_results"
        )
        
        # 4. compliance_rate
        total_completed = await conn.fetchval("""
            SELECT COUNT(DISTINCT w.id) 
            FROM workflow_runs w 
            JOIN compliance_decisions cd ON w.id = cd.workflow_run_id 
            WHERE w.status = 'COMPLETED'
        """)
        
        total_passed = await conn.fetchval("""
            SELECT COUNT(DISTINCT w.id) 
            FROM workflow_runs w 
            JOIN compliance_decisions cd ON w.id = cd.workflow_run_id 
            WHERE w.status = 'COMPLETED' AND cd.overall_status = 'PASS'
        """)
        
        if total_completed == 0:
            compliance_rate = None
        else:
            compliance_rate = (total_passed / total_completed) * 100.0
            
        # 5. open_manual_reviews_count
        open_reviews = await conn.fetchval(
            "SELECT COUNT(*) FROM review_queue WHERE status = 'OPEN'"
        )
        
        # 6. pass_fail_distribution
        distribution_records = await conn.fetch("""
            SELECT cd.overall_status, COUNT(w.id) as count 
            FROM workflow_runs w 
            JOIN compliance_decisions cd ON w.id = cd.workflow_run_id 
            WHERE w.status = 'COMPLETED' 
            GROUP BY cd.overall_status
        """)
        pass_fail_distribution = {r['overall_status']: r['count'] for r in distribution_records}
        
        # 7. top_violated_regulations
        top_violations = await conn.fetch("""
            SELECT r.code as regulation_code, COUNT(s.id) as count 
            FROM screening_results s 
            JOIN regulations r ON s.regulation_id = r.id 
            WHERE s.status IN ('RESTRICTED', 'THRESHOLD_EXCEEDED') 
            GROUP BY r.code 
            ORDER BY count DESC, r.code ASC 
            LIMIT 5
        """)
        top_violated_regulations = [{"regulation_code": r['regulation_code'], "count": r['count']} for r in top_violations]
        
        # 8. most_common_restricted_substances
        common_substances = await conn.fetch("""
            SELECT i.canonical_name, COUNT(s.id) as count 
            FROM screening_results s 
            JOIN ingredients i ON s.ingredient_id = i.id 
            WHERE s.status IN ('RESTRICTED', 'THRESHOLD_EXCEEDED') 
            GROUP BY i.canonical_name 
            ORDER BY count DESC, i.canonical_name ASC 
            LIMIT 5
        """)
        most_common_restricted_substances = [{"canonical_name": r['canonical_name'], "count": r['count']} for r in common_substances]

    return {
        "products_screened_count": products_screened,
        "ingredients_identified_count": ingredients_identified,
        "regulations_evaluated_count": regulations_evaluated,
        "compliance_rate": compliance_rate,
        "open_manual_reviews_count": open_reviews,
        "pass_fail_distribution": pass_fail_distribution,
        "top_violated_regulations": top_violated_regulations,
        "most_common_restricted_substances": most_common_restricted_substances
    }
