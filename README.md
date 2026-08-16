# Autonomous Code Review & Verification Agent

> Don't just tell developers what might be wrong. Investigate it and prove it.

An autonomous agent that reviews GitHub pull requests like a senior software engineer:
**Observe → Understand → Plan → Investigate → Reproduce → Verify → Recommend → Re-test**

---

## What it does

When a PR is opened, the agent:

1. **Indexes** the repository using AST parsing (Tree-sitter) and builds a dependency graph
2. **Analyzes impact** — identifies which callers, dependents, API consumers, and tests may be affected
3. **Spawns specialized agents** in parallel:
   - **Bug Agent** — logic errors, type coercions, race conditions, null dereferences
   - **Security Agent** — SQL injection, command injection, SSRF, hardcoded secrets (via data-flow tracing)
   - **Performance Agent** — N+1 queries, O(n²) algorithms, memory accumulation
4. **Generates minimal reproduction tests** for high-confidence findings
5. **Executes tests** inside an isolated Docker sandbox (no network, CPU/memory limits)
6. **Runs self-review** — discards speculative, duplicate, or style-only findings
7. **Posts evidence-backed findings** as inline GitHub PR comments

Every finding has an evidence level:
| Level | Meaning |
|-------|---------|
| `potential` | Suspected through static analysis |
| `evidence_backed` | Supported by code/repository evidence |
| `reproduced` | A generated test confirmed the issue |
| `fixed_and_verified` | Patch applied, tests pass |

---

## Architecture

```
GitHub Webhook
    ↓
FastAPI Webhook Handler
    ↓
arq Background Worker
    ↓
Review Orchestrator
    ↓
Repository Context Builder
    ├── Tree-sitter AST Parser
    ├── Dependency Graph (networkx)
    ├── GitHub API (files, diffs, history)
    └── Impact Analysis
    ↓
Specialized Agents (parallel)
    ├── Bug Agent
    ├── Security Agent
    └── Performance Agent
    ↓
Test Agent (per finding)
    ↓
Docker Sandbox (isolated execution)
    ↓
Self-Review Agent (quality gate)
    ↓
GitHub Publisher (PR comments + check runs)
    ↓
PostgreSQL (findings, timeline, evidence)
```

---

## Quick Start

### Prerequisites

- Docker & Docker Compose
- A GitHub App ([create one](https://github.com/settings/apps/new))
- OpenAI API key

### 1. Clone and configure

```bash
git clone <repo>
cd coderev
cp .env.example .env
# Edit .env with your credentials
```

### 2. GitHub App setup

Create a GitHub App with:
- **Permissions**: Pull requests (read/write), Contents (read), Checks (write), Issues (read)
- **Webhook events**: Pull requests
- **Webhook URL**: `https://your-domain.com/api/v1/webhooks/github`

Download the private key PEM and set `GITHUB_APP_PRIVATE_KEY_PATH` in `.env`.

### 3. Start

```bash
docker-compose up --build
```

- Backend API: http://localhost:8000
- Frontend: http://localhost:3000
- API docs: http://localhost:8000/docs

---

## Development

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example .env

# Run DB migrations
alembic upgrade head

# Start API
uvicorn app.main:app --reload

# Start worker
python -m arq app.worker.WorkerSettings
```

### Run tests

```bash
cd backend
pytest tests/ -v
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

---

## Benchmark

Evaluate the agent against historical bugs:

```python
from app.benchmark.runner import run_benchmark
import asyncio

summary = asyncio.run(run_benchmark())
print(f"Precision: {summary.precision}")
print(f"Recall: {summary.recall}")
print(f"F1: {summary.f1}")
print(f"Reproduction rate: {summary.reproduction_rate}")
```

---

## Project Structure

```
coderev/
├── backend/
│   ├── app/
│   │   ├── agents/          # Specialized investigation agents
│   │   │   ├── base.py      # Agent base class (state, retry, tool dispatch)
│   │   │   ├── bug_agent.py
│   │   │   ├── security_agent.py
│   │   │   ├── performance_agent.py
│   │   │   ├── test_agent.py
│   │   │   ├── self_review_agent.py
│   │   │   └── tools.py     # Shared agent tools
│   │   ├── api/v1/          # FastAPI routes
│   │   ├── benchmark/       # Evaluation framework
│   │   ├── core/            # Config, DB, Redis, logging
│   │   ├── github/          # GitHub App auth + client
│   │   ├── intelligence/    # AST parser, dependency graph, repo context
│   │   ├── llm/             # LLM client (OpenAI)
│   │   ├── models/          # SQLAlchemy models
│   │   ├── orchestrator/    # Review orchestrator (main pipeline)
│   │   ├── publisher/       # GitHub comment/check publisher
│   │   ├── sandbox/         # Docker sandbox executor
│   │   ├── schemas/         # Pydantic response schemas
│   │   └── worker/          # arq background jobs
│   └── tests/
└── frontend/
    ├── app/                 # Next.js App Router pages
    ├── components/          # React components
    └── lib/                 # API client, utilities
```

---

## Key Design Principles

- **Evidence over assertion** — agents must cite code before reporting an issue
- **Precision over quantity** — 2 verified findings beat 20 speculative ones
- **Repository-level reasoning** — impact analysis beyond the changed lines
- **Isolated execution** — no untrusted code runs on the host
- **Structured agent state** — findings carry evidence, tests, and reproduction status
- **Self-review gate** — a final agent discards weak findings before publishing
