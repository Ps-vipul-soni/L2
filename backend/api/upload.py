import os
import shutil
import uuid
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request

router = APIRouter()

SUPPORTED_EXTENSIONS = {".pdf", ".csv", ".xls", ".xlsx", ".xml"}

@router.post("/upload")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    product_id: str = Form(...)
):
    # Validate product_id is a valid UUID to prevent DB errors
    try:
        uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid product_id format. Must be a UUID.")
        
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type '{ext}'. Allowed types are {SUPPORTED_EXTENSIONS}")
        
    doc_type = "SDS"
    if ext in [".csv", ".xlsx", ".xls"]:
        doc_type = "BOM"
    elif ext == ".xml":
        doc_type = "FMD"
        
    # Generate unique filename to avoid collisions
    unique_filename = f"{uuid.uuid4()}{ext}"
    upload_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../storage/uploads'))
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, unique_filename)
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
        
    pool = request.app.state.pool
    
    async with pool.acquire() as conn:
        try:
            document_id = await conn.fetchval(
                """
                INSERT INTO documents (product_id, doc_type, filename, file_path)
                VALUES ($1, $2, $3, $4)
                RETURNING id
                """,
                product_id, doc_type, file.filename, file_path
            )
        except Exception as e:
            # Clean up the file if DB insert fails (e.g. invalid product_id that isn't in products table)
            if os.path.exists(file_path):
                os.remove(file_path)
            raise HTTPException(status_code=400, detail=f"Database error. Product ID may not exist. {str(e)}")
            
    return {"document_id": str(document_id), "message": "Document uploaded successfully"}
