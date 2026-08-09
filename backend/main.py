import os
import sys
import asyncpg
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
load_dotenv(os.path.join(os.path.dirname(__file__), '../.env'))

from backend.api.upload import router as upload_router
from backend.api.pipeline import router as pipeline_router
from backend.api.products import router as products_router
from backend.api.reports import router as reports_router
from backend.api.dashboard import router as dashboard_router
from backend.api.screening_results import router as screening_results_router
from backend.api.suppliers import router as suppliers_router
from neo4j import AsyncGraphDatabase

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL environment variable is not set")
        
    app.state.pool = await asyncpg.create_pool(db_url, min_size=1, max_size=5)
    print("Database connection pool established.")
    
    neo4j_uri = os.environ.get("NEO4J_URI")
    neo4j_user = os.environ.get("NEO4J_USERNAME")
    neo4j_pass = os.environ.get("NEO4J_PASSWORD")
    if neo4j_uri:
        app.state.neo4j_driver = AsyncGraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_pass))
        print("Neo4j driver established.")
    
    yield
    
    # Shutdown
    await app.state.pool.close()
    print("Database connection pool closed.")
    if hasattr(app.state, 'neo4j_driver'):
        await app.state.neo4j_driver.close()
        print("Neo4j driver closed.")

app = FastAPI(title="Compliance Screening API", lifespan=lifespan)

# Create storage/uploads directory if it doesn't exist
os.makedirs(os.path.abspath(os.path.join(os.path.dirname(__file__), '../storage/uploads')), exist_ok=True)

app.include_router(upload_router, prefix="/documents", tags=["Documents"])
app.include_router(pipeline_router, prefix="/pipeline", tags=["Pipeline"])
app.include_router(products_router, prefix="/products", tags=["Products"])
app.include_router(reports_router, prefix="/reports", tags=["Reports"])
app.include_router(dashboard_router)
app.include_router(screening_results_router)
app.include_router(suppliers_router)

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/health/neo4j")
async def health_check_neo4j(request: Request):
    neo4j_driver = getattr(request.app.state, 'neo4j_driver', None)
    if not neo4j_driver:
        return {"status": "disconnected", "detail": "Driver not initialized"}
    
    try:
        async with neo4j_driver.session() as session:
            # Trivial query to check connectivity
            result = await session.run("RETURN 1 AS ping")
            record = await result.single()
            if record and record["ping"] == 1:
                return {"status": "connected"}
    except Exception as e:
        return {"status": "disconnected", "detail": str(e)}
        
    return {"status": "disconnected", "detail": "Ping failed"}
