# Agentic Supply Chain Compliance AI

**Intelligent Regulatory Knowledge Assistant** — an autonomous, multi-agent AI pipeline that ingests raw supply chain documents, performs complex compliance evaluations (RoHS, REACH, Prop 65), and maps supply chain risk into a queryable graph database.

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![Streamlit](https://img.shields.io/badge/Streamlit-1.41-FF4B4B.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16.0-336791.svg)
![Neo4j](https://img.shields.io/badge/Neo4j-5.27-018bff.svg)
![LangGraph](https://img.shields.io/badge/LangGraph-AI-green.svg)

---

## Overview
Managing supply chain compliance is traditionally a highly manual, error-prone process. Reviewing Safety Data Sheets (SDS) against hundreds of changing regulations takes hours per document. This project completely automates this process using a **CQRS (Command Query Responsibility Segregation) Architecture**:

- **System of Record (PostgreSQL):** Transactional storage for documents, extraction results, and human-in-the-loop review queues.
- **Read-Side Analytics (Neo4j):** Deterministic supply chain tracing to identify exactly which Tier-1 suppliers are exposing the product portfolio to restricted chemicals.

The evaluation logic is driven by a LangGraph multi-agent state machine, preventing hallucinations through external tool-calling and strict programmatic thresholds.

## Key Features
- **Multi-Agent Orchestration (LangGraph):** Dedicated AI agents for Document Extraction, Regulation Planning, and Compliance Screening.
- **Dynamic Conditional Routing:** Automatically routes low-confidence extractions or subjective regulatory rules (like California Prop 65 exposure limits) to a Human-in-the-Loop Review Queue.
- **External API Tool-Calling:** Integrates with the NIH PubChem API via MCP (Model Context Protocol) to definitively resolve chemical names to standardized CAS numbers—eliminating AI hallucination.
- **Idempotent Graph Synchronization:** A robust pipeline (`load_graph.py`) to flawlessly synchronize relational data into a Neo4j AuraDB graph topology without duplication.
- **Complex Regulatory Logic:** Differentiates between strict concentration thresholds (RoHS/REACH) and additive customer-specific Restricted Substance Lists (RSLs).

## Tech Stack
| Layer | Technology |
|---|---|
| Frontend | Streamlit |
| Backend API | FastAPI |
| AI Orchestration | LangGraph |
| LLMs | Google Gemini 3.5 Pro & 3.1 Flash |
| External Tooling | PubChem MCP Client |
| Transactional DB | PostgreSQL + asyncpg |
| Graph Database | Neo4j AuraDB |

## Architecture
```text
                                ┌─────────────────────────┐
                                │   Streamlit Frontend    │
                                │   (User UI & Polling)   │
                                └───────────┬─────────────┘
                                            │ REST API
                                ┌───────────▼─────────────┐
                                │     FastAPI Backend     │
                                └───────────┬─────────────┘
                                            │
    ┌───────────────────────────────────────▼───────────────────────────────────────┐
    │                         LANGGRAPH AI ORCHESTRATOR                             │
    │                                                                               │
    │  ┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐      │
    │  │ Doc Extractor   │ ────► │ Reg Planner     │ ────► │ Comp. Screener  │      │
    │  │ (Gemini Pro)    │       │ (Gemini Flash)  │       │ (Gemini Pro)    │      │
    │  └──────┬──────────┘       └──────┬──────────┘       └───────┬─────────┘      │
    │         │                         │                          │                │
    │         │ (Low Confidence)        │                          │                │
    │  ┌──────▼──────────┐              │                          │                │
    │  │ Review Queue    │              │                          │                │
    │  │ (Human in loop) │              │                          │                │
    │  └─────────────────┘              │                          │                │
    └───────────────────────────────────┼──────────────────────────┼────────────────┘
               │                        │                          │
               │ (Resolves CAS)         │ (Target Geographies)     │ (Save Results)
       ┌───────▼───────┐                │                          │
       │  MCP Client   │ ───────────────┼──────────────────────────┤
       │ (PubChem API) │                │                          │
       └───────────────┘                │                          │
                                        ▼                          ▼
                               ┌─────────────────────────────────────────┐
                               │       PostgreSQL (System of Record)     │
                               │   (Products, Components, Ingredients)   │
                               └────────────────┬────────────────────────┘
                                                │
                                                │ load_graph.py (asyncpg + neo4j)
                                                │ Idempotent Graph Sync (MERGE)
                                                ▼
                               ┌─────────────────────────────────────────┐
                               │     Neo4j AuraDB (Read-Side Graph)      │
                               │  (Supplier Risk & Exposure Analytics)   │
                               └─────────────────────────────────────────┘
```

## Prerequisites
- Python 3.11+
- A running PostgreSQL instance
- A Neo4j AuraDB Free Instance
- A Google Gemini API key

## Quickstart

### 1. Clone the repo
```bash
git clone <your-repository-url>
cd <repository-directory>
```

### 2. Configure environment variables
Copy the example env file and fill in your credentials:
```bash
cp .env.example .env
```
*(On Windows PowerShell, use: `Copy-Item .env.example .env`)*

Update the `.env` file with your actual keys:
```bash
GEMINI_API_KEY=your_google_gemini_key_here
DATABASE_URL=postgresql://user:password@localhost:5432/dbname
NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_neo4j_password_here
```

### 3. Install dependencies
```bash
cd backend
python -m venv .venv
# Windows
.\.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 4. Start the backend (FastAPI)
```bash
cd backend
uvicorn main:app --reload --port 8000
```
The API will be available at `http://localhost:8000`.

### 5. Start the frontend (Streamlit)
In a second terminal:
```bash
cd frontend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt

streamlit run app.py
```
The app opens automatically at `http://localhost:8501`.

## Project Structure
```text
project_root/
├── backend/
│   ├── agents/          # LangGraph state machine and AI agents
│   ├── graph_db/        # Neo4j integration and sync scripts
│   ├── database/        # PostgreSQL schema (schema_v1_draft.sql)
│   ├── main.py          # FastAPI application
│   └── requirements.txt
├── frontend/
│   ├── app.py           # Streamlit UI
│   └── requirements.txt
├── scratch/             # Analytical scripts (e.g. supplier_risk.py)
├── .env                 # Environment credentials (Git-ignored)
├── .gitignore
└── README.md
```

## Disclaimer
This is a demonstration of Agentic AI architectures. It is **not** a substitute for certified legal or environmental compliance testing. Always consult qualified compliance officers before deploying supply chain products.
