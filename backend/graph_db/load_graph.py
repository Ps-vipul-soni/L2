import asyncio
import os
import asyncpg
from neo4j import GraphDatabase
from dotenv import load_dotenv

# Load environment variables
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../.env')))

NEO4J_URI = os.environ.get("NEO4J_URI")
NEO4J_USERNAME = os.environ.get("NEO4J_USERNAME")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD")
PG_URL = os.environ.get("DATABASE_URL")

class GraphLoader:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        
    def close(self):
        self.driver.close()
        
    def execute_write(self, cypher_query, parameters=None):
        with self.driver.session() as session:
            result = session.run(cypher_query, parameters)
            summary = result.consume()
            return summary.counters

async def load_data():
    if not NEO4J_URI or not PG_URL:
        print("Missing required environment variables for DB connection.")
        return

    print("Connecting to PostgreSQL...")
    conn = await asyncpg.connect(PG_URL)
    
    print("Connecting to Neo4j AuraDB...")
    neo4j_loader = GraphLoader(NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD)
    
    try:
        # 1. Fetch data from PostgreSQL
        print("Fetching data from PostgreSQL...")
        
        # Suppliers
        suppliers = await conn.fetch("SELECT id, name FROM suppliers")
        
        # Products
        products = await conn.fetch("SELECT id, name FROM products")
        
        # Components
        components = await conn.fetch("SELECT id, product_id, name, supplier_id FROM components")
        
        # Ingredients
        ingredients = await conn.fetch("SELECT id, cas_number, canonical_name FROM ingredients")
        
        # Component-Ingredients
        component_ingredients = await conn.fetch("SELECT component_id, ingredient_id FROM component_ingredients")
        
        print(f"Fetched {len(suppliers)} suppliers, {len(products)} products, {len(components)} components, {len(ingredients)} ingredients, {len(component_ingredients)} relationships.")
        
        # 2. Push to Neo4j (Idempotent MERGE)
        print("Syncing nodes to Neo4j...")
        
        # Suppliers
        for s in suppliers:
            neo4j_loader.execute_write(
                """
                MERGE (s:Supplier {pg_id: $id})
                ON CREATE SET s.name = $name
                ON MATCH SET s.name = $name
                """, 
                {"id": str(s['id']), "name": s['name']}
            )
            
        # Products
        for p in products:
            neo4j_loader.execute_write(
                """
                MERGE (pr:Product {pg_id: $id})
                ON CREATE SET pr.name = $name
                ON MATCH SET pr.name = $name
                """, 
                {"id": str(p['id']), "name": p['name']}
            )
            
        # Components
        for c in components:
            neo4j_loader.execute_write(
                """
                MERGE (cp:Component {pg_id: $id})
                ON CREATE SET cp.name = $name
                ON MATCH SET cp.name = $name
                """, 
                {"id": str(c['id']), "name": c['name']}
            )
            
        # Ingredients
        for i in ingredients:
            neo4j_loader.execute_write(
                """
                MERGE (ing:Ingredient {pg_id: $id})
                ON CREATE SET ing.name = $name, ing.cas_number = $cas
                ON MATCH SET ing.name = $name, ing.cas_number = $cas
                """, 
                {"id": str(i['id']), "name": i['canonical_name'], "cas": i['cas_number']}
            )
            
        print("Syncing relationships to Neo4j...")
        
        # Product -[:CONTAINS]-> Component
        # Component -[:SOURCED_FROM]-> Supplier
        for c in components:
            if c['product_id']:
                neo4j_loader.execute_write(
                    """
                    MATCH (pr:Product {pg_id: $p_id})
                    MATCH (cp:Component {pg_id: $c_id})
                    MERGE (pr)-[:CONTAINS]->(cp)
                    """,
                    {"p_id": str(c['product_id']), "c_id": str(c['id'])}
                )
            if c['supplier_id']:
                neo4j_loader.execute_write(
                    """
                    MATCH (cp:Component {pg_id: $c_id})
                    MATCH (s:Supplier {pg_id: $s_id})
                    MERGE (cp)-[:SOURCED_FROM]->(s)
                    """,
                    {"c_id": str(c['id']), "s_id": str(c['supplier_id'])}
                )
                
        # Component -[:USES]-> Ingredient
        for ci in component_ingredients:
            neo4j_loader.execute_write(
                """
                MATCH (cp:Component {pg_id: $c_id})
                MATCH (ing:Ingredient {pg_id: $i_id})
                MERGE (cp)-[:USES]->(ing)
                """,
                {"c_id": str(ci['component_id']), "i_id": str(ci['ingredient_id'])}
            )
            
        print("Graph sync complete!")
        
        # Test query to count nodes and relationships
        counts = neo4j_loader.execute_write(
            """
            MATCH (n)
            OPTIONAL MATCH (n)-[r]->()
            RETURN count(DISTINCT n) as nodes, count(r) as relationships
            """
        )
        # We need to run a read transaction to get results
        with neo4j_loader.driver.session() as session:
            result = session.run("MATCH (n) OPTIONAL MATCH (n)-[r]->() RETURN count(DISTINCT n) as nodes, count(r) as relationships")
            record = result.single()
            print(f"AuraDB stats: {record['nodes']} nodes, {record['relationships']} relationships")

    finally:
        await conn.close()
        neo4j_loader.close()

if __name__ == "__main__":
    asyncio.run(load_data())
