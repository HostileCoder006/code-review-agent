# Autonomous Code Review & Verification Agent

> Don't just tell developers what might be wrong. Investigate it and prove it.

An autonomous agent that reviews GitHub pull requests like a senior software engineer:
**Observe → Understand → Plan → Investigate → Reproduce → Verify → Recommend → Re-test**

---

## What it does

When a PR is opened, the agent:

1. **Indexes** the repository using AST parsing (Tree-sitter) and builds a dependency graph
2. **Analyzes impact** — identifies which callers, dependents, API consumers, and tests are affected
3. **Spawns specialized agents** in parallel:
   - **Bug Agent** — logic errors, type coercions, race conditions, null dereferences
   - **Security Agent** — SQL injection, command injection, SSRF, hardcoded secrets (data-flow tracing)
   - **Performance Agent** — N+1 queries, O(n²) algorithms, memory accumulation
4. **Generates minimal reproduction tests** for high-confidence findings
5. **Executes tests** in an isolated Python venv (no Docker needed)
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
arq Background Worker (Redis)
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
Venv Sandbox (isolated Python venv per test)
    ↓
Self-Review Agent (quality gate)
    ↓
GitHub Publisher (PR comments + check runs)
    ↓
PostgreSQL (findings, timeline, evidence)
```

---

## Requirements

- **Python 3.11+** — https://python.org
- **Node.js 20+** — https://nodejs.org
- **PostgreSQL 15+** — https://www.postgresql.org/download/windows/
- **Redis** — `winget install Redis.Redis` or https://github.com/microsoftarchive/redis/releases
- **OpenRouter API key** — https://openrouter.ai/keys
- **GitHub App** — https://github.com/settings/apps/new
- **ngrok** (for webhook tunnel) — https://ngrok.com/download

---

## Quick Start (Windows)

### 1. Clone the repo

```bat
git clone https://github.com/HostileCoder006/code-review-agent.git
cd code-review-agent
```

### 2. Configure environment

```bat
copy .env.example .env
```

Edit `.env` with your credentials:

```env
GITHUB_APP_ID=your_app_id
GITHUB_APP_PRIVATE_KEY_PATH=./github-app.pem
GITHUB_WEBHOOK_SECRET=your_webhook_secret
OPENAI_API_KEY=sk-or-...
OPENAI_MODEL=anthropic/claude-haiku-4-5
OPENAI_BASE_URL=https://openrouter.ai/api/v1
DATABASE_URL=postgresql+asyncpg://coderev:coderev@localhost:5432/coderev
REDIS_URL=redis://localhost:6379/0
SANDBOX_WORKSPACE_DIR=C:\Users\YOUR_USERNAME\coderev_sandboxes
SECRET_KEY=any-random-string
```

Copy your GitHub App `.pem` file to the project root as `github-app.pem`.

### 3. Install dependencies

```bat
scripts\setup.bat
```

### 4. Set up the database

Make sure PostgreSQL is running, then:

```bat
scripts\setup-db.bat
```

### 5. Start ngrok tunnel

```bat
ngrok http 8000
```

Copy the `https://xxx.ngrok-free.app` URL and set it as your GitHub App's webhook URL:
```
https://xxx.ngrok-free.app/api/v1/webhooks/github
```

### 6. Start everything

```bat
scripts\start-all.bat
```

This opens 3 terminal windows:
- **Backend** → http://localhost:8000
- **Worker** → background job processor
- **Frontend** → http://localhost:3000

### 7. Install GitHub App on a repo

Go to https://github.com/settings/apps → click your app → **Install App** → pick a repo.

Open a Pull Request in that repo and watch the agent run at **http://localhost:3000**.

---

## Running services individually

```bat
:: Backend API
scripts\start-backend.bat

:: Background worker (separate terminal)
scripts\start-worker.bat

:: Frontend
scripts\start-frontend.bat
```

---

## Development

### Backend tests

```bat
cd backend
venv\Scripts\activate
pytest tests\ -v
```

### Run the benchmark

```python
from app.benchmark.runner import run_benchmark
import asyncio

summary = asyncio.run(run_benchmark())
print(f"Precision: {summary.precision}")
print(f"Recall:    {summary.recall}")
print(f"F1:        {summary.f1}")
print(f"Reproduced:{summary.reproduction_rate}")
```

---

## Project Structure

```
code-review-agent/
├── scripts/
│   ├── setup.bat          # Install all dependencies
│   ├── setup-db.bat       # Create DB + run migrations
│   ├── start-all.bat      # Launch all 3 services
│   ├── start-backend.bat  # FastAPI backend
│   ├── start-worker.bat   # arq background worker
│   └── start-frontend.bat # Next.js frontend
├── backend/
│   ├── app/
│   │   ├── agents/        # Bug, Security, Performance, Test, Self-Review agents
│   │   ├── api/v1/        # FastAPI routes (webhooks, reviews, findings, stats)
│   │   ├── benchmark/     # Precision/recall evaluation framework
│   │   ├── core/          # Config, DB, Redis, logging
│   │   ├── github/        # GitHub App auth + REST client
│   │   ├── intelligence/  # AST parser, dependency graph, repo context builder
│   │   ├── llm/           # OpenRouter LLM client
│   │   ├── models/        # SQLAlchemy models
│   │   ├── orchestrator/  # Main review pipeline
│   │   ├── publisher/     # GitHub PR comment + check run publisher
│   │   ├── sandbox/       # Isolated venv test executor
│   │   ├── schemas/       # Pydantic schemas
│   │   └── worker/        # arq job definitions
│   └── tests/
└── frontend/
    ├── app/               # Next.js pages (dashboard, reviews, repos, stats)
    ├── components/        # React components
    └── lib/               # API client, utilities
```

---

## Key Design Principles

- **Evidence over assertion** — agents cite actual code before reporting an issue
- **Precision over quantity** — 2 verified findings beat 20 speculative ones
- **Repository-level reasoning** — impact analysis beyond just the changed lines
- **Isolated execution** — each test runs in a throwaway Python venv
- **Structured agent state** — findings carry evidence, tests, and reproduction status
- **Self-review gate** — a final agent discards weak findings before publishing
