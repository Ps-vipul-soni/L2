-- ============================================================
-- Compliance Screening System — Phase 1 Schema (FINAL)
-- ============================================================
-- Design notes:
-- 1. products -> components -> ingredients mirrors the eventual
--    Neo4j graph (Product -contains-> Component -uses-> Ingredient,
--    Component -sourced_from-> Supplier), so Phase 4 is a data
--    migration, not a redesign.
-- 2. ingredients is a canonical table; ingredient_synonyms holds
--    raw names as extracted, resolved to a canonical ingredient_id
--    by the Chemical Normalization tool node.
-- 3. regulation_thresholds is versioned (effective_date, source_url,
--    retrieved_at) from day one.
-- 4. screening_results and compliance_decisions are kept separate:
--    one row per (component, ingredient, regulation) screening
--    outcome, aggregated up into one decision per product.
-- 5. review_queue exists from Phase 1 so the confidence-based
--    human-review branch (Phase 2) has a table to write to.
-- 6. workflow_runs tracks one row per screening execution; screening_
--    results, compliance_decisions, and reports carry a workflow_run_id
--    so everything from one run can be grouped. documents deliberately
--    does NOT carry a workflow_run_id — documents are reusable across
--    runs since a document may be rescreened when regulation lists
--    update. A workflow_run_documents join table can be added later
--    if per-run document usage needs direct tracking.
-- 7. screening_results.confidence is distinct from documents.
--    extraction_confidence — one scores extraction quality, the other
--    scores the screening judgment itself (e.g. exemption applicability).
--    Both can independently trigger review_queue routing.
-- 8. risk_score stays inline on compliance_decisions; a separate
--    risk_assessments table is deferred until more than one
--    risk-related field is needed.
-- 9. retry_of_run_id deliberately omitted from workflow_runs — deferred
--    until retry logic is actually implemented, not speculatively
--    designed for.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ---------- Suppliers ----------
CREATE TABLE suppliers (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            TEXT NOT NULL,
    country         TEXT,
    contact_email   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- Products ----------
CREATE TABLE products (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            TEXT NOT NULL,
    sku             TEXT UNIQUE,
    product_type    TEXT,           -- e.g. 'electronics', 'cosmetics' — drives Regulation Planning
    customer_name   TEXT,           -- for customer-specific RSLs (Phase 3)
    market_country  TEXT,           -- Added in Phase 3 for jurisdiction filtering
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- Workflow runs (one row per compliance screening execution) ----------
CREATE TABLE workflow_runs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id      UUID NOT NULL REFERENCES products(id),
    status          TEXT NOT NULL CHECK (status IN ('RUNNING','COMPLETED','FAILED','PARTIAL')),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ
);

-- ---------- Workflow Run Documents (Many-to-Many traceability) ----------
CREATE TABLE workflow_run_documents (
    workflow_run_id UUID NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    PRIMARY KEY (workflow_run_id, document_id)
);

CREATE INDEX idx_wrd_document_id ON workflow_run_documents(document_id);

CREATE TABLE tool_call_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_run_id UUID REFERENCES workflow_runs(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ---------- Components (BOM line items within a product) ----------
CREATE TABLE components (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id      UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    supplier_id     UUID REFERENCES suppliers(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_components_product ON components(product_id);
CREATE INDEX idx_components_supplier ON components(supplier_id);

-- ---------- Ingredients (canonical, post-normalization) ----------
CREATE TABLE ingredients (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    canonical_name  TEXT NOT NULL,
    cas_number      TEXT UNIQUE,     -- nullable: some substances have no CAS #
    pubchem_cid     TEXT,            -- reference back to source lookup
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_ingredients_cas ON ingredients(cas_number);

-- ---------- Synonyms (raw extracted names -> canonical ingredient) ----------
CREATE TABLE ingredient_synonyms (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ingredient_id   UUID NOT NULL REFERENCES ingredients(id) ON DELETE CASCADE,
    raw_name        TEXT NOT NULL,
    UNIQUE (ingredient_id, raw_name)
);

-- ---------- Source documents (SDS/BOM/FMD uploads) ----------
CREATE TABLE documents (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id      UUID REFERENCES products(id),
    doc_type        TEXT NOT NULL CHECK (doc_type IN ('SDS','BOM','FMD','SUPPLIER_DECLARATION')),
    filename        TEXT NOT NULL,
    file_path       TEXT NOT NULL,
    uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    extraction_confidence NUMERIC(4,3),  -- 0.000–1.000, drives Phase 2 human-review routing
    extraction_notes TEXT                -- Optional notes from Document Understanding (Task 6)
    -- No workflow_run_id here by design: documents are reusable across runs
    -- (a document may be rescreened when regulation lists update). If
    -- per-run document usage needs tracking later, add a
    -- workflow_run_documents join table rather than an FK on this table.
);

-- ---------- Component <-> Ingredient (with extracted concentration) ----------
CREATE TABLE component_ingredients (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    component_id        UUID NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    ingredient_id        UUID NOT NULL REFERENCES ingredients(id),
    concentration_value NUMERIC(10,5),
    concentration_unit  TEXT CHECK (concentration_unit IN ('%','ppm','mg/kg')),
    source_document_id  UUID REFERENCES documents(id),
    UNIQUE (component_id, ingredient_id, source_document_id)
);

CREATE INDEX idx_comp_ing_component ON component_ingredients(component_id);
CREATE INDEX idx_comp_ing_ingredient ON component_ingredients(ingredient_id);

-- ---------- Regulations ----------
CREATE TABLE regulations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code            TEXT UNIQUE NOT NULL,   -- 'RoHS', 'REACH_SVHC', etc.
    name            TEXT NOT NULL,
    jurisdiction    TEXT,                   -- 'EU', 'US-CA', 'Global'
    applies_to_product_types TEXT[],        -- e.g. ARRAY['electronics'] — used by Regulation Planning (Phase 3)
    customer_name   TEXT                    -- Added in Phase 3 for customer-specific RSLs
);

-- ---------- Regulation thresholds (versioned) ----------
CREATE TABLE regulation_thresholds (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    regulation_id   UUID NOT NULL REFERENCES regulations(id),
    ingredient_id   UUID NOT NULL REFERENCES ingredients(id),
    threshold_value NUMERIC(10,5) NOT NULL,
    threshold_unit  TEXT NOT NULL CHECK (threshold_unit IN ('%','ppm','mg/kg')),
    exemption_notes TEXT,
    effective_date  DATE NOT NULL,
    source_url      TEXT NOT NULL,
    retrieved_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (regulation_id, ingredient_id, effective_date)
);

CREATE INDEX idx_reg_thresholds_ingredient ON regulation_thresholds(ingredient_id);

-- ---------- Screening results (per component/ingredient/regulation) ----------
CREATE TABLE screening_results (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_run_id         UUID NOT NULL REFERENCES workflow_runs(id),
    component_id            UUID NOT NULL REFERENCES components(id),
    ingredient_id           UUID NOT NULL REFERENCES ingredients(id),
    regulation_id           UUID NOT NULL REFERENCES regulations(id),
    status                  TEXT NOT NULL CHECK (status IN
                              ('RESTRICTED','ALLOWED','THRESHOLD_EXCEEDED','EXEMPTION_AVAILABLE','NEEDS_REVIEW')),
    measured_value          NUMERIC(10,5),
    threshold_value         NUMERIC(10,5),
    confidence              NUMERIC(4,3),    -- 0.000–1.000, distinct from documents.extraction_confidence:
                                              -- this scores confidence in the *screening judgment* (e.g.
                                              -- exemption applicability), not the *extraction*. Below-threshold
                                              -- values route to review_queue.
    reasoning               TEXT,            -- explainability: why this status
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_screening_component ON screening_results(component_id);
CREATE INDEX idx_screening_workflow_run ON screening_results(workflow_run_id);

-- ---------- Compliance decisions (aggregated per product) ----------
CREATE TABLE compliance_decisions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_run_id UUID NOT NULL REFERENCES workflow_runs(id),
    product_id      UUID NOT NULL REFERENCES products(id),
    overall_status  TEXT NOT NULL CHECK (overall_status IN ('PASS','FAIL','WARNING','REVIEW_REQUIRED')),
    risk_score      NUMERIC(5,2),            -- e.g. 0-100 — kept inline; separate risk_assessments
                                              -- table deferred until more than one risk-related field exists
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_compliance_decisions_workflow_run ON compliance_decisions(workflow_run_id);

-- ---------- Reports ----------
CREATE TABLE reports (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_run_id         UUID NOT NULL REFERENCES workflow_runs(id),
    compliance_decision_id  UUID NOT NULL REFERENCES compliance_decisions(id),
    executive_summary       TEXT,
    file_path               TEXT,            -- generated PDF/markdown location
    generated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_reports_workflow_run ON reports(workflow_run_id);

-- ---------- Human review queue (Phase 2 target, table exists from Phase 1) ----------
CREATE TABLE review_queue (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id     UUID REFERENCES documents(id),
    screening_result_id UUID REFERENCES screening_results(id),
    reason          TEXT NOT NULL,           -- e.g. 'low extraction confidence', 'ambiguous exemption'
    status          TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','RESOLVED','DISMISSED')),
    resolved_at     TIMESTAMPTZ,
    -- This column was added in Review Queue V2.
    -- It tracks review queue creation time going forward.
    -- Existing rows are backfilled with the migration execution time.
    -- Therefore existing rows do NOT have historically accurate creation timestamps.
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
