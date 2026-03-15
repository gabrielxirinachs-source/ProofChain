# 🔗 ProofChain Fact-Check

> A multi-source, multi-agent fact-checking engine that produces **auditable evidence graphs** instead of "trust me" summaries.

ProofChain verifies claims by assembling a structured chain of evidence from open knowledge graphs + live web sources — every verdict is backed by a traceable, inspectable graph of facts.

---

## 🏗️ Architecture Overview

```
Claim Input
    │
    ▼
┌─────────────────────────────────────────┐
│           LangGraph Agent Loop          │
│  ┌──────────┐  ┌──────────┐  ┌───────┐ │
│  │ KG Query │→ │  Expand  │→ │  Web  │ │
│  │(Wikidata)│  │  Nodes   │  │Search │ │
│  └──────────┘  └──────────┘  └───────┘ │
│         ↓ state: evidence graph         │
│  ┌──────────────────────────────────┐   │
│  │   Contradiction + Confidence     │   │
│  └──────────────────────────────────┘   │
└─────────────────────────────────────────┘
    │
    ▼
POST /verify → { verdict, evidence_graph, citations, confidence, failure_modes }
    │
    ▼
React UI — Interactive Evidence Graph (supporting ✅ / contradicting ❌ edges)
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| API | Python, FastAPI |
| Agent Orchestration | LangGraph |
| Evidence Store | PostgreSQL + pgvector |
| Semantic Search | pgvector / Qdrant |
| Web Retrieval | Playwright + trafilatura |
| Caching | Redis |
| Observability | OpenTelemetry |
| Containerization | Docker + Docker Compose |
| Frontend | Vite + React |
| Deployment | Fly.io / Render |

---

## 🗺️ Development Roadmap

- [x] **Phase 1** — Project scaffold, Docker, FastAPI skeleton
- [x] **Phase 2** — Graph-first evidence store (Postgres schema + pgvector)
- [x] **Phase 3** — Wikidata knowledge graph retrieval
- [x] **Phase 4** — Web retrieval completion (Playwright + trafilatura)
- [x] **Phase 5** — MDP-style LangGraph agent loop
- [x] **Phase 6** — Verification API (`/verify` endpoint)
- [x] **Phase 7** — Observability + production deploy
- [x] **Phase 8** — React frontend with interactive evidence graph

---

## 🚀 Getting Started

### Prerequisites
- Docker Desktop
- Python 3.11+
- Git

### Run Locally

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/proofchain.git
cd proofchain

# Copy environment variables
cp .env.example .env

# Start all services
docker compose up --build

# API will be live at:
# http://localhost:8000
# Docs at: http://localhost:8000/docs
```

### Running without Docker (backend only)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate       # Windows WSL: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

---

## 📁 Project Structure

```
proofchain/
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI route handlers
│   │   ├── agents/       # LangGraph agent definitions
│   │   ├── core/         # Config, settings, constants
│   │   ├── db/           # Database connections + migrations
│   │   ├── models/       # Pydantic + SQLAlchemy models
│   │   └── services/     # Business logic (KG retrieval, web fetch, scoring)
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/   # React components
│   │   ├── pages/        # Page-level components
│   │   ├── hooks/        # Custom React hooks
│   │   └── lib/          # API client, utils
│   └── package.json
├── infra/                # Docker, deployment configs
├── docs/                 # Architecture notes, diagrams
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## 📄 License

MIT