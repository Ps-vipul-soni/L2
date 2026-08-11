# 🛡️ Agentic Supply Chain Compliance AI

**Intelligent Regulatory Knowledge Assistant** — an autonomous, multi-agent AI pipeline that ingests raw supply chain documents (BOMs, SDS, FMDs), performs complex compliance evaluations (RoHS, REACH, Prop 65), and maps supply chain risk into a queryable graph database.

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![Streamlit](https://img.shields.io/badge/Streamlit-1.41-FF4B4B.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16.0-336791.svg)
![Neo4j](https://img.shields.io/badge/Neo4j-5.27-018bff.svg)
![LangGraph](https://img.shields.io/badge/LangGraph-AI-green.svg)

---

## 📑 Table of Contents
- [Overview](#-overview)
- [Key Features](#-key-features)
- [Architecture](#-architecture)
- [Technology Stack](#-technology-stack)
- [Quickstart Guide](#-quickstart-guide)
- [Project Structure](#-project-structure)
- [Disclaimer](#-disclaimer)

---

## 🔎 Overview

Managing supply chain compliance is traditionally a highly manual, error-prone process. Reviewing Safety Data Sheets (SDS) against hundreds of changing regulations takes hours per document. This project completely automates this process using a **CQRS (Command Query Responsibility Segregation) Architecture**:

- **System of Record (PostgreSQL):** Transactional storage for products, documents, extracted chemical components, screening results, and human-in-the-loop review queues.
- **Read-Side Analytics (Neo4j):** Deterministic supply chain tracing to identify exactly which Tier-1 suppliers are exposing the product portfolio to restricted chemicals, mapped as a graph.

The evaluation logic is driven by a **LangGraph multi-agent state machine**, which prevents LLM hallucinations through explicit tool-calling, strict programmatic thresholds, and batched contextual reasoning.

---

## ✨ Key Features

- **Multi-Agent Orchestration (LangGraph):** Dedicated AI agents handle Document Extraction, Chemical Normalization, Regulation Planning, and Compliance Screening in an automated DAG.
- **Multi-Document Aggregation:** Synthesizes ingredients across multiple concurrent supplier documents into a single portfolio screening run.
- **Batched LLM Explanability:** Implements intelligent prompt-batching to provide human-readable compliance reasoning while staying efficiently under API rate limits.
- **Dynamic Conditional Routing:** Automatically routes low-confidence extractions or messy PDF parsing to a Human-in-the-Loop Review Queue rather than forcing an unsafe automated decision.
- **External API Tool-Calling (MCP):** Integrates with the NIH PubChem API and local Regulatory databases via **Model Context Protocol (MCP)** servers to definitively resolve chemical names to standardized CAS numbers—eliminating AI hallucination.
- **Comprehensive UI:** An 8-page Streamlit frontend encompassing Dashboards, Product Screening, Supplier Risk Analytics, Compliance Reporting, and Queue Management.

---

## 🏗️ Architecture

```mermaid
graph TD
    classDef frontend fill:#3b82f6,stroke:#2563eb,stroke-width:2px,color:#fff;
    classDef api fill:#10b981,stroke:#059669,stroke-width:2px,color:#fff;
    classDef orchestrator fill:#8b5cf6,stroke:#7c3aed,stroke-width:2px,color:#fff;
    classDef agent fill:#f59e0b,stroke:#d97706,stroke-width:2px,color:#fff;
    classDef mcp fill:#ef4444,stroke:#dc2626,stroke-width:2px,color:#fff;
    classDef database fill:#64748b,stroke:#475569,stroke-width:2px,color:#fff;

    UI[Streamlit Frontend]:::frontend -->|REST API| API[FastAPI Backend]:::api
    
    API -->|Orchestrates| Graph[LangGraph AI Orchestrator]:::orchestrator
    API -->|Reads/Writes| Postgres[(PostgreSQL)]:::database
    
    subgraph Agents [LangGraph State Machine]
        DocExt[Doc Extractor]:::agent
        RegPlan[Reg Planner]:::agent
        CompScreen[Comp Screener]:::agent
        RiskDec[Risk & Decision]:::agent
        RevQueue[Review Queue]:::agent
        
        DocExt --> RegPlan --> CompScreen --> RiskDec
        DocExt -.->|Low Confidence| RevQueue
    end
    
    Graph --> Agents
    
    subgraph MCP Servers
        AgentA[PubChem MCP]:::mcp
        AgentB[Regulation MCP]:::mcp
    end
    
    DocExt -->|Resolve CAS| AgentA
    CompScreen -->|Query Rules| AgentB
    
    Agents -->|Dual Write| Postgres
    Agents -->|Graph Map| Neo4j[(Neo4j AuraDB)]:::database
```

---

## 💻 Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Frontend** | Streamlit | 8-Page Interactive Web Application |
| **Backend API** | FastAPI | High-performance REST API |
| **AI Orchestration** | LangGraph | State Machine & Agent Routing |
| **LLMs** | Google Gemini 3.1 Flash | Extraction & Explanability Reasoning |
| **External Tooling** | MCP (Model Context Protocol) | External Data Tooling Interfaces |
| **Transactional DB** | PostgreSQL + asyncpg | Core relational system of record |
| **Graph Database** | Neo4j AuraDB | Supply chain impact and hierarchy |

---

## 🚀 Quickstart Guide

### 1. Prerequisites
- Python 3.11+
- A running PostgreSQL instance (v16+)
- A Neo4j AuraDB Free Instance
- A Google Gemini API key

### 2. Clone the Repository
```bash
git clone <your-repository-url>
cd <repository-directory>
```

### 3. Configure Environment Variables
Create a `.env` file in the root of the project with your actual credentials:
```bash
GEMINI_API_KEY=your_google_gemini_key_here
DATABASE_URL=postgresql://user:password@localhost:5432/dbname
NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_neo4j_password_here
```

### 4. Start the Backend API
Open a terminal in the project root:
```bash
cd backend
python -m venv .venv

# Windows
.\.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```
The API will be available at `http://localhost:8000`.

### 5. Start the Frontend UI
Open a **second terminal** in the project root:
```bash
cd frontend
python -m venv .venv

# Windows
.\.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
streamlit run frontend/1_Dashboard.py
```
The UI opens automatically at `http://localhost:8501`.

---

## 📂 Project Structure

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
│   ├── pages/           # Streamlit UI routing components
│   ├── 1_Dashboard.py   # Streamlit entrypoint
│   └── requirements.txt
├── mcp_servers/         # Model Context Protocol servers
│   ├── chemical_identity_mcp/
│   └── regulation_lookup_mcp/
├── .env                 # Environment credentials (Not checked into source)
└── README.md            # You are here
```

---

## ⚠️ Disclaimer
This is a technical demonstration of Agentic AI architectures. It is **not** a substitute for certified legal or environmental compliance testing. Always consult qualified compliance officers before deploying products into restricted supply chains.
