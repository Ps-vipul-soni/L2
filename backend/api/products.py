from fastapi import APIRouter, Request, HTTPException, status
from pydantic import BaseModel
from typing import Optional
import asyncpg

class ProductCreate(BaseModel):
    name: str
    sku: str
    product_type: str
    market_country: str
    customer_name: Optional[str] = None

router = APIRouter()

@router.get("")
async def list_products(request: Request):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        products = await conn.fetch("SELECT id, name, sku, product_type, market_country, customer_name FROM products ORDER BY name ASC")
        
        results = []
        for p in products:
            results.append({
                "id": str(p["id"]),
                "name": p["name"],
                "sku": p["sku"],
                "product_type": p["product_type"],
                "market_country": p["market_country"],
                "customer_name": p["customer_name"]
            })
        return results

@router.post("")
async def create_product(product: ProductCreate, request: Request):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO products (name, sku, product_type, market_country, customer_name)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id, name, sku, product_type, market_country, customer_name
                """,
                product.name, product.sku, product.product_type, product.market_country, product.customer_name
            )
            return {
                "id": str(row["id"]),
                "name": row["name"],
                "sku": row["sku"],
                "product_type": row["product_type"],
                "market_country": row["market_country"],
                "customer_name": row["customer_name"]
            }
        except asyncpg.exceptions.UniqueViolationError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A product with SKU '{product.sku}' already exists."
            )
