# Antigravity Phase 3 Knowledge Base

## Overview
This knowledge base documents the current state of the Antigravity Regulatory Compliance engine as of the completion of Phase 3. It serves as the source of truth for subsequent agents (Phase 4+) to ensure architectural decisions and schema extensions are preserved and not accidentally reverted or re-derived.

## 1. Supported Regulations
The system's `regulations` table currently models exactly 5 regulatory frameworks. The legacy copy-pasted test data has been strictly purged.

1. **RoHS** (`jurisdiction='EU'`): Percentage-based restrictions (e.g. 0.1% Lead, 0.01% Cadmium) for electronics.
2. **REACH_SVHC** (`jurisdiction='EU'`): Broad chemical reporting and restriction framework applicable across multiple product types (electronics, cosmetics, general articles).
3. **TSCA_SEC6** (`jurisdiction='US'`): US federal regulations under the Toxic Substances Control Act Section 6, enforcing strict PBT bans (e.g. 0% DecaBDE). Note: The legacy generic `TSCA` row was invalid and deleted.
4. **PROP_65** (`jurisdiction='US-CA'`): California state law requiring exposure warnings. In our DB schema, this is modeled via `0 ppm` threshold placeholders with the true MADL/NSRL exposure limit explicitly noted in the `exemption_notes` column, to prevent incorrect percentage-based failures. 
5. **ACME_RSL_2026** (`jurisdiction='Global'`, `customer_name='Acme Corp'`): A synthetic, customer-scoped Restricted Substance List containing ultra-strict constraints (e.g. 0.05% Lead) that only applies to products manufactured for Acme Corp.

*(Note: SCIP is a reporting obligation, not a separate threshold list, and its legacy threshold rows were confirmed invalid and purged).*

## 2. Schema Extensions (Phase 3)
To support dynamic Regulation Planning, the schema was officially locked and extended with two critical columns without altering the foundational tables:

- **`products.market_country` (String, Nullable):** Defines the target regional jurisdiction where a product will be sold (e.g., `'EU'`, `'US'`). Used by the planner to cross-reference against a regulation's `jurisdiction`.
- **`regulations.customer_name` (String, Nullable):** Used to isolate proprietary, customer-specific Restricted Substance Lists (RSLs). If populated, this regulation will strictly only apply to products sharing the exact same `customer_name`.

## 3. The Regulation Planning Node
Prior to Phase 3, the `Compliance Screening` node was hardcoded to run only `RoHS` and `REACH_SVHC`. This has been completely overhauled.

The system now utilizes an independent LangGraph node called **Regulation Planning** (`backend/agents/regulation_planning.py`), which executes immediately prior to Compliance Screening.

### Role & Execution Flow
1. **Goal:** Determine precisely which regulations apply to the current product, outputting an `applicable_regulations` array to the state dictionary.
2. **Deterministic-First Matching:** The node prioritizes hard-coded, deterministic rule checks. 
   - A regulation applies if its `applies_to_product_types` is NULL/empty, or matches the product's type.
   - It applies if its `jurisdiction` is 'Global', or if its jurisdiction matches the product's `market_country`. (Note: A product with `market_country = NULL` is excluded from regional laws).
   - It applies if its `customer_name` is NULL, or strictly matches the product's `customer_name`.
3. **LLM Fallback:** The LLM is **only** invoked for fuzzy/ambiguous `product_type` resolution (e.g. if a product is "smart watch" but the regulation lists "electronics"), keeping the pipeline deterministic, fast, and legally defensible.
4. **Handoff:** The `Compliance Screening` node now dynamically loops over `state["applicable_regulations"]` rather than relying on hardcoded lists.
