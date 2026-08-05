import os
import sys
import asyncpg
from contextlib import asynccontextmanager
from fastapi import FastAPI
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
load_dotenv(os.path.join(os.path.dirname(__file__), '../.env'))

from backend.api.upload import router as upload_router
from backend.api.pipeline import router as pipeline_router
from backend.api.products import router as products_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL environment variable is not set")
        
    app.state.pool = await asyncpg.create_pool(db_url, min_size=1, max_size=5)
    print("Database connection pool established.")
    
    yield
    
    # Shutdown
    await app.state.pool.close()
    print("Database connection pool closed.")

app = FastAPI(title="Compliance Screening API", lifespan=lifespan)

# Create storage/uploads directory if it doesn't exist
os.makedirs(os.path.abspath(os.path.join(os.path.dirname(__file__), '../storage/uploads')), exist_ok=True)

app.include_router(upload_router, prefix="/documents", tags=["Documents"])
app.include_router(pipeline_router, prefix="/pipeline", tags=["Pipeline"])
app.include_router(products_router, prefix="/products", tags=["Products"])

@app.get("/health")
async def health_check():
    return {"status": "ok"}
