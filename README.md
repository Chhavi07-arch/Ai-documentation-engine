# 🧠 AI-Powered Developer Documentation Engine

> Ingest a GitHub repository → parse its code → generate professional documentation with LLMs → detect when code drifts from its docs → draft updates → and chat with a documentation-aware assistant.

A production-style, full-stack MVP that behaves like a real developer-productivity startup tool. Built with **Next.js + FastAPI + OpenRouter + ChromaDB**.

---

## ✨ Features

| # | Feature | What it does |
|---|---------|--------------|
| 1 | **GitHub ingestion** | Clone & validate a public GitHub repo, scan Python source, build a file tree (GitPython). |
| 2 | **AST parsing engine** | Extract functions, classes, methods, params, return types, decorators, docstrings, imports, async flags & type hints — never executes code. |
| 3 | **AI documentation** | Generate professional, handbook-style Markdown (overview, params, returns, raises, side effects, examples, edge cases) per entity. |
| 4 | **Change detection** | Structural, AST-aware snapshot diffing: signature/param/return/body changes, renames, additions, deletions — not naive text diffing. |
| 5 | **Staleness engine** | Classifies impacted docs as `BROKEN`, `POTENTIALLY_OUTDATED`, or `REVIEW_RECOMMENDED` with color-coded badges. |
| 6 | **Update drafting** | Re-drafts docs from old code + new code + existing docs, with a polished unified-diff viewer. |
| 7 | **Docs website** | Premium dark UI: dashboard, repo overview, docs explorer, file/function view, stale center, chat, settings. Command palette (⌘K), skeletons, responsive. |
| 8 | **RAG chatbot** | Answers strictly from the docs (chunking → embeddings → ChromaDB → retrieval → LLM), cites sources, and says *"Information not found in documentation"* when unsure. |

> **Works without an API key.** If `OPENROUTER_API_KEY` is unset, the engine falls back to deterministic doc generation and a local embedding model — so the whole product is demoable offline.

---

## 🏗️ Architecture

```
┌──────────────────────────┐         REST / JSON          ┌────────────────────────────┐
│        Frontend          │  ───────────────────────────▶ │          Backend           │
│  Next.js (App Router)    │                               │          FastAPI           │
│  TypeScript · Tailwind   │ ◀─────────────────────────── │  routers → services → db   │
│  shadcn/ui · TanStack    │                               │  parsers · rag · diffing   │
└──────────────────────────┘                               └─────────────┬──────────────┘
                                                                          │
                                          ┌───────────────┬──────────────┼───────────────┐
                                          ▼               ▼              ▼               ▼
                                     SQLite (ORM)   OpenRouter LLM   ChromaDB      GitHub (clone)
```

**Backend layering:** `routers` (HTTP) → `services` (business logic) → `models`/`schemas` (data) with focused helpers in `parsers`, `rag`, `diffing`, `prompts`, `core`, `utils`.

---

## 🧰 Tech Stack

**Frontend:** Next.js 14 (App Router), TypeScript, Tailwind CSS, shadcn/ui, Lucide, TanStack Query, next-themes, react-markdown.

**Backend:** Python 3.11, FastAPI, Uvicorn, SQLAlchemy 2.0 (SQLite), Pydantic v2, GitPython, ChromaDB, httpx.

**AI:** OpenRouter (OpenAI-compatible), configurable chat & embedding models, with local fallbacks.

---

## 📁 Project Structure

```
.
├── backend/
│   ├── app/
│   │   ├── core/        # config, database, exceptions, logging
│   │   ├── models/      # SQLAlchemy ORM models + enums
│   │   ├── schemas/     # Pydantic request/response models
│   │   ├── parsers/     # AST parsing engine (extensible, language-agnostic base)
│   │   ├── services/    # ingestion, doc-gen, change-detection, staleness, rag
│   │   ├── rag/         # chunking, embeddings, ChromaDB vector store
│   │   ├── diffing/     # AST entity diff + unified text diff
│   │   ├── prompts/     # centralized, reusable prompt templates
│   │   ├── routers/     # REST endpoints
│   │   └── main.py      # FastAPI app
│   ├── tests/           # pytest: parser, diffing, API
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── app/             # routes: dashboard, repositories, docs, stale, chat, settings
│   ├── components/      # ui (shadcn), layout, shared
│   ├── features/        # feature modules (repositories, docs, stale, chat)
│   ├── hooks/           # TanStack Query hooks
│   ├── lib/ · services/ # API client + typed endpoint layer
│   └── Dockerfile
├── docs_storage/        # generated markdown (gitignored)
├── vector_storage/      # ChromaDB persistence (gitignored)
├── repositories/        # cloned repos (gitignored)
└── docker-compose.yml
```

---

## 🚀 Quickstart (local)

### Prerequisites
- Python **3.11+**, Node **18+**, and **git** installed.

### 1) Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env        # then add your OPENROUTER_API_KEY (optional)
# --reload-dir app scopes the auto-reloader to your source only; without it,
# uvicorn watches .venv too and restarts mid-request on stray .pyc writes.
uvicorn app.main:app --reload --reload-dir app --port 8000
```

API runs at **http://localhost:8000** · interactive docs at **http://localhost:8000/docs**.

### 2) Frontend

```bash
cd frontend
npm install
cp .env.example .env.local   # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

App runs at **http://localhost:3000**.

### 3) Try it
1. Click **Add repository** and paste a public Python GitHub URL (e.g. `https://github.com/psf/requests`).
2. Wait for status → **Ready**, then hit **Generate docs**.
3. Explore docs, open **AI Chat**, or run **Detect changes** → **Stale Center**.

---

## 🐳 Run everything with Docker

```bash
OPENROUTER_API_KEY=sk-or-... docker compose up --build
# frontend → http://localhost:3000   backend → http://localhost:8000
```

---

## 🔐 Environment Variables

### Backend (`backend/.env`)
| Variable | Default | Description |
|----------|---------|-------------|
| `OPENROUTER_API_KEY` | _(empty)_ | OpenRouter key. Empty → local fallbacks. |
| `OPENROUTER_MODEL` | `anthropic/claude-sonnet-4-6` | Chat/generation model. |
| `OPENROUTER_EMBEDDING_MODEL` | `openai/text-embedding-3-small` | Embedding model. |
| `DATABASE_URL` | `sqlite:///./docengine.db` | SQLAlchemy database URL. |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins. |

### Frontend (`frontend/.env.local`)
| Variable | Default | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend base URL (no trailing slash). |

---

## 📡 API Reference

Base path: `/api`

| Method | Route | Description |
|--------|-------|-------------|
| `POST` | `/repositories/ingest` | Queue clone + parse of a GitHub repo (async). |
| `GET`  | `/repositories` | List repositories. |
| `GET`  | `/repositories/{id}` | Repository detail + file tree. |
| `GET`  | `/repositories/{id}/entities` | List parsed entities. |
| `GET`  | `/repositories/entities/{entity_id}` | Full entity detail. |
| `POST` | `/generate-docs` | Generate documentation for a repo. |
| `GET`  | `/docs/{entity_id}` | Get documentation for an entity. |
| `POST` | `/detect-changes` | Snapshot + structural change detection. |
| `GET`  | `/stale-docs` | List staleness flags. |
| `POST` | `/draft-update` | Draft an updated doc + unified diff. |
| `POST` | `/chat` | Ask the documentation-aware chatbot. |
| `GET`  | `/stats` · `/config` · `/health` | Dashboard stats, AI config, health. |

Errors are returned uniformly as `{ "error": { "code", "message" } }`.

---

## 🧪 Testing

```bash
cd backend && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```

Covers the AST parser, change-detection classification (incl. rename detection), and the HTTP API surface.

---

## ☁️ Deployment

- **Frontend → Vercel:** import the repo, set root to `frontend/`, add `NEXT_PUBLIC_API_URL`.
- **Backend → Render/Railway:** Docker deploy from `backend/` (a `render.yaml` blueprint and `Procfile` are included). Set `OPENROUTER_API_KEY` and `CORS_ORIGINS` (your Vercel URL).

---

## 🧭 How It Works (pipeline)

```
Ingest:   clone → scan *.py → AST parse → persist entities → baseline snapshot
Generate: entity → prompt template → OpenRouter → Markdown → store + index in ChromaDB
Detect:   re-parse → structural diff vs latest snapshot → staleness flags (severity)
Draft:    old code + new code + existing docs → revised Markdown + unified diff
Chat:     question → embed → retrieve top-k chunks → grounded LLM answer + sources
```

---

## 📝 Notes & Scope

- **MVP scope:** Python repositories. The parser layer is abstracted (`BaseParser`) so additional languages can be added without touching the rest of the system.
- **Safety:** repository URLs are validated, files are size-bounded, vendored/hidden dirs are skipped, and **code is never executed** — only its AST is analyzed.
- Generated artifacts (`docs_storage/`, `vector_storage/`, `repositories/`, `*.db`) are gitignored.

---

Built as a polished, demo-ready collaborative engineering project. 🚀
