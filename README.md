# WorkStory AI

A local, AI-powered workspace that turns an engineer's pull-request history into a structured, searchable experience library — and uses it for evidence-backed technical interview preparation.

> 🚧 Work in progress.

## Modules

1. **My Experience** — browse projects, skills and engineering categories reconstructed from PRs.
2. **Experience Assistant** — ask questions about your work; answers cite the projects and PRs they come from (hybrid RAG).
3. **Interview Prep** — role-, JD- and project-based interview questions with on-demand answers labelled as experience-backed, partially backed or knowledge-based.

## Repository layout

| Path          | Purpose                                                   |
| ------------- | --------------------------------------------------------- |
| `backend/`    | Python + FastAPI API, ingestion and RAG pipeline          |
| `frontend/`   | Next.js + TypeScript UI                                   |
| `extraction/` | Schema, validator and tooling to build the experience JSON |
| `examples/`   | Synthetic sample dataset used for development and demos   |
| `eval/`       | Retrieval and answer-quality evaluation                   |
| `data/`       | Your private experience data — **git-ignored, never committed** |

## Stack

Python · FastAPI · PostgreSQL · pgvector · Next.js · Ollama (local LLM + embeddings) · Docker

## Local development

Requirements: Docker, [uv](https://docs.astral.sh/uv/), Node.js 20+, [Ollama](https://ollama.com).

```bash
# Local models (one-time download, ~5 GB)
ollama serve            # or open the Ollama app
ollama pull nomic-embed-text
ollama pull llama3.1:8b
```

```bash
# 1. Start PostgreSQL + pgvector (host port 5433)
docker compose up -d

# 2. Install backend dependencies and run migrations
cd backend
uv sync
uv run alembic upgrade head

# 3. Run the API  →  http://localhost:8000/health  ·  docs at /docs
uv run uvicorn app.main:app --reload

# Tests (database tests are skipped if Postgres isn't running)
uv run pytest

# Validate an experience file
uv run workstory-validate ../examples/sample-experience.json

# Import it into the database and embed its chunks (CLI, or POST /imports while the API runs)
uv run workstory-import ../examples/sample-experience.json

# Embed any chunks still missing embeddings (e.g. if Ollama was off during import)
uv run workstory-embed
curl -F "file=@../examples/sample-experience.json" localhost:8000/imports
```

```bash
# 4. Run the web app (in another terminal)  →  http://localhost:3000
cd frontend
npm install
npm run dev
```

The web app reads the API from `API_URL` (default `http://localhost:8000`).

Imports are snapshots: records missing from the file are removed, and re-importing
an unchanged file is a no-op (`--force` / `?force=true` to re-import anyway).

## Privacy

All data stays on your machine. Real experience files live in `data/` and are excluded from version control.
