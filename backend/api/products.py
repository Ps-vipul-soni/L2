from fastapi import APIRouter, Request

router = APIRouter()

@router.get("")
async def list_products(request: Request):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        products = await conn.fetch("SELECT id, name FROM products ORDER BY name ASC")
        
        results = []
        for p in products:
            results.append({
                "id": str(p["id"]),
                "name": p["name"]
            })
        return results
