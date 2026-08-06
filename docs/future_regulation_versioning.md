# Future Enhancement: Regulation Versioning & Immutability

**Status:** DEFERRED (Pending Phase 1 Schema Lock Expiration)  
**Component:** Database Schema (`regulations`, `regulation_thresholds`)  

## 1. The Danger of Hard Deletes in Compliance Systems
In a legal compliance engine, regulations are never truly "deleted"—they are superseded, amended, or retired. Relying on standard `DELETE` SQL commands to remove legacy or outdated regulations is operationally fragile. 

Physical deletion creates severe Foreign Key constraint violations against historical data (e.g., `screening_results` that reference the deleted regulation). To execute a hard delete, the system is forced to either cascade the deletion (which illegally destroys historical compliance audit trails) or block the deletion entirely, leading to system lockups.

## 2. Why `deprecated_at` is Preferred Over `is_active`
To solve the hard-delete problem, we must implement a soft-delete mechanism. We evaluated two common patterns:
*   **The `is_active` Boolean Flag:** While simple to query (`WHERE is_active = TRUE`), this approach destroys historical context. If an auditor asks why a product passed compliance in 2024 but failed in 2026, an `is_active = FALSE` flag cannot tell them exactly *when* the rule was deactivated.
*   **The `deprecated_at` Timestamp:** This is the gold standard for compliance. The regulation remains in the database forever, ensuring historical `screening_results` perfectly join to the exact regulation state active at the time. Furthermore, the timestamp provides an exact, legally defensible audit trail of precisely when the requirement was retired.

## 3. Future Regulation Planning Node Architecture
Once implemented, the `Regulation Planning` node will be updated to filter out retired regulations dynamically. The base query in `backend/agents/regulation_planning.py` will evolve from:
```sql
SELECT code, jurisdiction, applies_to_product_types, customer_name FROM regulations
```
to:
```sql
SELECT code, jurisdiction, applies_to_product_types, customer_name 
FROM regulations 
WHERE deprecated_at IS NULL OR deprecated_at > CURRENT_TIMESTAMP
```
This ensures the planner only scopes active regulations for newly screened products, while preserving all historical foreign key relationships.

## 4. Rationale for Deferment
This enhancement has been explicitly designed, approved in concept, and intentionally **deferred** until a future phase. 

One of the project's core design principles is to rigidly preserve the finalized Phase 1 schema unless an immediate implementation requirement makes evolution unavoidable. For Phase 3, the Regulation Planning node can operate correctly on the existing schema, provided legacy rows are handled via one-off operational cleanup scripts. 

Therefore, the `deprecated_at` schema evolution is documented here to ensure future engineers understand the architectural intent and can implement it safely when the Phase 1 schema lock is eventually lifted.
