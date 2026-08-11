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
- [Multi-Agent System (LangGraph)](#-multi-agent-system-langgraph)
- [MCP Servers (Model Context Protocol)](#-mcp-servers-model-context-protocol)
- [Architecture](#-architecture)
- [Technology Stack](#-technology-stack)
- [Quickstart Guide](#-quickstart-guide)
- [Disclaimer](#-disclaimer)

---

## 🔎 Overview

Managing supply chain compliance is traditionally a highly manual, error-prone process. Reviewing Safety Data Sheets (SDS) against hundreds of changing regulations takes hours per document. This project completely automates this process using a **CQRS (Command Query Responsibility Segregation) Architecture**:

- **System of Record (PostgreSQL):** Transactional storage for products, documents, extracted chemical components, screening results, and human-in-the-loop review queues.
- **Read-Side Analytics (Neo4j):** Deterministic supply chain tracing to identify exactly which Tier-1 suppliers are exposing the product portfolio to restricted chemicals, mapped as a graph.

The evaluation logic is driven by a **LangGraph multi-agent state machine**, which prevents LLM hallucinations through explicit tool-calling via MCP, strict programmatic thresholds, and batched contextual reasoning.

---

## 🤖 Multi-Agent System (LangGraph)

The pipeline uses a coordinated team of AI agents, each strictly scoped to a specific compliance phase:

1. **Document Understanding Agent:** Extracts complex hierarchical Bill of Materials (BOM) and Full Material Declaration (FMD) data from raw supplier PDFs/CSVs. It intelligently aggregates multi-document submissions into a single cohesive product graph.
2. **Regulation Planning Agent:** Determines exactly which regulations apply to the product based on its target jurisdiction (e.g., California Prop 65, EU RoHS) and product type, dramatically reducing unnecessary screening overhead.
3. **Compliance Screening Agent:** The core evaluation engine. It batches LLM prompts to analyze the extracted ingredients against the planned regulations, validating constraints safely beneath Gemini's rate limits while remaining 100% deterministic.
4. **Risk & Decision Agent:** Synthesizes the screening results to calculate an overall product compliance status (PASS, FAIL, WARNING) and identifies critical supply-chain vulnerabilities.
5. **Review Routing Agent (Human-in-the-Loop):** Acts as a safety valve. If the Document Understanding agent expresses low confidence (e.g., due to a blurry PDF), this agent halts the automated pipeline and routes the document to a UI Review Queue for human validation.
6. **Report Generation Agent:** Drafts an executive summary of the compliance outcome tailored for stakeholders.

---

## 🔌 MCP Servers (Model Context Protocol)

To eliminate AI hallucinations, the agents are not permitted to "guess" chemical facts or regulatory limits. Instead, they are equipped with two distinct **MCP (Model Context Protocol)** servers that provide standardized tool-calling interfaces:

- **Agent A (Chemical Identity MCP):** A specialized server that connects to the **NIH PubChem API**. Whenever the Document Understanding agent reads a chemical name like "Lead" or "H2O", it calls this MCP server to definitively resolve the name to its canonical CAS Registry Number and known synonyms.
- **Agent B (Regulation Lookup MCP):** A specialized server that holds the deterministic truth regarding compliance thresholds. The Compliance Screening agent uses this server to query the exact permitted parts-per-million (PPM) for a chemical under a specific regulation. 

By offloading factual lookups to MCP servers, the LLMs are restricted solely to text-extraction and logical reasoning, guaranteeing regulatory accuracy.

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
        AgentA[Chemical Identity MCP]:::mcp
        AgentB[Regulation Lookup MCP]:::mcp
    end
    
    DocExt -->|Resolve CAS via PubChem| AgentA
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

## ⚠️ Disclaimer
This is a technical demonstration of Agentic AI architectures. It is **not** a substitute for certified legal or environmental compliance testing. Always consult qualified compliance officers before deploying products into restricted supply chains.
