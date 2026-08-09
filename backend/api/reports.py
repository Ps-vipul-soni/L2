import os
import re
import csv
import io
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response

router = APIRouter()

def parse_markdown_report(file_path: str) -> dict:
    """Parses the generated markdown file into a structured dictionary of sections."""
    if not os.path.exists(file_path):
        return {}
        
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Split by markdown headers
    sections = {}
    
    # Use regex to find ## Headers and their content
    # The regex looks for "## <Header Name>\n<Content>" up to the next "##" or EOF
    matches = re.finditer(r"##\s+(.*?)\n(.*?)(?=\n##\s+|\Z)", content, re.DOTALL)
    
    for match in matches:
        header = match.group(1).strip()
        body = match.group(2).strip()
        
        # Convert header to snake_case key
        key = header.lower().replace(" ", "_")
        sections[key] = body
        
    return sections

@router.get("/recent")
async def get_recent_reports(request: Request):
    """Fetches recently completed workflow runs that have reports."""
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        runs = await conn.fetch("""
            SELECT w.id, w.completed_at, p.name as product_name
            FROM workflow_runs w
            JOIN products p ON w.product_id = p.id
            JOIN reports r ON r.workflow_run_id = w.id
            WHERE w.status = 'COMPLETED'
            ORDER BY w.completed_at DESC
            LIMIT 10
        """)
        return [dict(run) for run in runs]

@router.get("/{workflow_run_id}/export")
async def export_report(request: Request, workflow_run_id: str, format: str = "json"):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        run = await conn.fetchrow("SELECT id, status, started_at, completed_at FROM workflow_runs WHERE id = $1", workflow_run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Workflow run not found")
            
        decision = await conn.fetchrow("SELECT overall_status, risk_score FROM compliance_decisions WHERE workflow_run_id = $1", workflow_run_id)
        report_row = await conn.fetchrow("SELECT executive_summary, file_path FROM reports WHERE workflow_run_id = $1", workflow_run_id)
        
        screening_records = await conn.fetch("""
            SELECT 
                c.name as component_name,
                i.canonical_name as ingredient_name,
                r.name as regulation_name,
                sr.measured_value,
                sr.threshold_value,
                sr.status,
                sr.confidence,
                sr.reasoning
            FROM screening_results sr
            JOIN components c ON sr.component_id = c.id
            JOIN ingredients i ON sr.ingredient_id = i.id
            JOIN regulations r ON sr.regulation_id = r.id
            WHERE sr.workflow_run_id = $1
            ORDER BY c.name, i.canonical_name
        """, workflow_run_id)
        
        screening_results = [dict(sr) for sr in screening_records]

        if format == "csv":
            # Generate CSV
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["Component", "Ingredient", "Regulation", "Measured Value", "Allowed Limit", "Status", "Confidence", "Reasoning"])
            
            for sr in screening_results:
                writer.writerow([
                    sr["component_name"],
                    sr["ingredient_name"],
                    sr["regulation_name"],
                    sr["measured_value"],
                    sr["threshold_value"],
                    sr["status"],
                    sr["confidence"],
                    sr["reasoning"]
                ])
                
            return Response(
                content=output.getvalue(),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename=screening_results_{workflow_run_id}.csv"}
            )
            
        elif format == "json":
            # Generate Relational JSON Entity Map
            
            # Parse Markdown to reconstruct the generated fields
            parsed_report = {}
            if report_row and report_row["file_path"]:
                parsed_report = parse_markdown_report(report_row["file_path"])
            
            # Ensure executive summary is at least there from DB
            if "executive_summary" not in parsed_report and report_row:
                parsed_report["executive_summary"] = report_row["executive_summary"]

            payload = {
                "workflow_run": dict(run),
                "compliance_decision": dict(decision) if decision else None,
                "report": parsed_report,
                "screening_results": screening_results
            }
            return payload
            
        else:
            raise HTTPException(status_code=400, detail="Invalid format. Use 'json' or 'csv'.")
