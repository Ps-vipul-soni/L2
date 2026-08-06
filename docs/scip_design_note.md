# Design Note: SCIP Database & Proposition 65 Modeling

This document captures the architectural decisions made during Phase 3 regarding the modeling of the EU SCIP Database and California's Proposition 65 within the existing Phase 1 database schema (`schema_v1_draft.sql`).

## 1. SCIP Database Architecture

### The Regulatory Reality
The SCIP (Substances of Concern In articles as such or in complex objects (Products)) database is an EU reporting obligation established under the Waste Framework Directive. It requires suppliers to submit notifications for products placed on the EU market that contain Substances of Very High Concern (SVHCs) on the **REACH Candidate List** in a concentration above **0.1% w/w**.

### Architectural Decision
- **No Duplicate Thresholds:** SCIP does *not* introduce its own unique list of restricted substances or varying threshold limits. It relies 100% on the REACH SVHC list and the 0.1% threshold.
- **Database Modeling:** Therefore, we have inserted a row into the `regulations` table (Code: `SCIP`), but we explicitly do **not** seed rows into `regulation_thresholds` for SCIP.
- **Agent Implementation Guidance:** The Compliance Screening Agent (Agent C) should evaluate SCIP compliance by executing the screening logic against the `REACH_SVHC` thresholds. If a product fails REACH SVHC (an ingredient exceeds 0.1% w/w), it inherently triggers the SCIP reporting obligation. Maintaining a parallel set of threshold rows for SCIP would introduce dangerous data duplication and maintenance overhead.

## 2. Proposition 65 Schema Compromises

### The Regulatory Reality
California's Proposition 65 requires warnings for exposure to chemicals that cause cancer or reproductive toxicity. OEHHA establishes "Safe Harbor Levels" (NSRLs and MADLs), which are measured as **exposure limits (e.g., µg/day)**, rather than concentration thresholds (e.g., % or ppm).

### Architectural Decision
- **Schema Rigidity:** The Phase 1 `regulation_thresholds` table was explicitly designed for concentration-based regulations like RoHS. It features strict `NOT NULL` constraints on `threshold_value` and a `CHECK` constraint restricting `threshold_unit` to only `('%', 'ppm', 'mg/kg')`.
- **System Workaround:** To preserve the immutable Phase 1 schema while ingesting Prop 65 data, we have modeled Prop 65 substances using a schema compatibility placeholder:
  - `threshold_value = 0`
  - `threshold_unit = 'ppm'`
- **Truth in Exemptions:** The actual regulatory meaning is recorded in the `exemption_notes` column. This includes the true Safe Harbor Level in µg/day (if one exists) or a note indicating "No Safe Harbor Level established."
- **Future Revisions:** These placeholder values (`0 ppm`) **MUST NOT** be interpreted programmatically as absolute concentration bans. The Compliance Screening agent should read the `exemption_notes` and flag Prop 65 detections for human review to assess exposure. In a future database schema revision, `threshold_value` and `threshold_unit` should be decoupled or made nullable to natively support exposure-based limits.
