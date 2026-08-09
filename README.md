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

- **System of Record (PostgreSQL):** Transactional storage for products, documents, extracted chemical components, and human-in-the-loop review queues.
- **Read-Side Analytics (Neo4j):** Deterministic supply chain tracing to identify exactly which Tier-1 suppliers are exposing the product portfolio to restricted chemicals, mapped as a graph.

The evaluation logic is driven by a **LangGraph multi-agent state machine**, preventing hallucinations through external tool-calling and strict programmatic thresholds.

## Key Features
- **Multi-Agent Orchestration (LangGraph):** Dedicated AI agents for Document Extraction, Chemical Normalization, Regulation Planning, and Compliance Screening.
- **Dynamic Conditional Routing:** Automatically routes low-confidence extractions or messy PDF parsing to a Human-in-the-Loop Review Queue.
- **External API Tool-Calling:** Integrates with the NIH PubChem API and local Regulatory databases via **MCP (Model Context Protocol)** servers to definitively resolve chemical names to standardized CAS numbers—eliminating AI hallucination.
- **8-Page Streamlit UI:** A fully featured frontend encompassing Dashboards, Product Screening, Supplier Risk Analytics, Compliance Reporting, and Queue Management.

## Tech Stack
| Layer | Technology |
|---|---|
| **Frontend** | Streamlit (Multi-page App) |
| **Backend API** | FastAPI |
| **AI Orchestration** | LangGraph |
| **LLMs** | Google Gemini 3.1 Flash Lite |
| **External Tooling** | `chemical_identity_mcp` & `regulation_lookup_mcp` |
| **Transactional DB** | PostgreSQL + asyncpg |
| **Graph Database** | Neo4j AuraDB |

## Architecture
```text
                                ┌─────────────────────────┐
                                │   Streamlit Frontend    │
                                │   (8-Page UI & Polling) │
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
    │  │ (3.1 Flash Lite)│       │ (3.1 Flash Lite)│       │ (3.1 Flash Lite)│      │
    │  └──────┬──────────┘       └──────┬──────────┘       └───────┬─────────┘      │
    │         │                         │                          │                │
    │         │ (Low Confidence)        │                          │                │
    │  ┌──────▼──────────┐              │                          │                │
    │  │ Review Queue    │              │                          │                │
    │  │ (Human in loop) │              │                          │                │
    │  └─────────────────┘              │                          │                │
    └───────────────────────────────────┼──────────────────────────┼────────────────┘
               │                        │                          │
               │ (Resolves CAS)         │ (Query Reg Rules)        │ (Save Results)
       ┌───────▼───────┐        ┌───────▼───────┐                  │
       │  MCP Server   │        │  MCP Server   │                  │
       │ (PubChem API) │        │ (Reg. Lookup) │                  │
       └───────────────┘        └───────┬───────┘                  │
                                        │                          │
                                        ▼                          ▼
                               ┌─────────────────────────────────────────┐
                               │       PostgreSQL (System of Record)     │
                               │   (Products, Components, Ingredients)   │
                               └────────────────┬────────────────────────┘
                                                │ (Dual-Write / Sync)
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
Create a `.env` file in the root of the project with your actual keys:
```bash
GEMINI_API_KEY=your_google_gemini_key_here
DATABASE_URL=postgresql://user:password@localhost:5432/dbname
NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_neo4j_password_here
```

### 3. Start the Backend API
Open a terminal in the project root:
```bash
cd backend
python -m venv .venv
# Windows
.\.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```
The API will be available at `http://localhost:8000`.

### 4. Start the Frontend UI
Open a **second terminal** in the project root:
```bash
cd frontend
python -m venv .venv
# Windows
.\.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
streamlit run frontend/streamlit_app.py
```
The UI opens automatically at `http://localhost:8501`.

## Project Structure
```text
project_root/
├── backend/
│   ├── agents/          # LangGraph state machine, nodes, and parsers
│   ├── api/             # FastAPI routers (dashboard, pipeline, products, etc.)
│   ├── graph/           # LangGraph configuration (pipeline_graph.py)
│   ├── utils/           # Database drivers and matching utilities
│   ├── main.py          # FastAPI application entrypoint
│   └── requirements.txt
├── frontend/
│   ├── pages/           # 8-page Streamlit UI routing
│   ├── streamlit_app.py # Streamlit entrypoint
│   └── requirements.txt
├── mcp_servers/         # Model Context Protocol servers
│   ├── chemical_identity_mcp/
│   └── regulation_lookup_mcp/
├── .env                 # Environment credentials
├── README.md
└── good_sds.pdf         # Sample document for testing
```

## Disclaimer
This is a demonstration of Agentic AI architectures. It is **not** a substitute for certified legal or environmental compliance testing. Always consult qualified compliance officers before deploying supply chain products.
