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

## Privacy

All data stays on your machine. Real experience files live in `data/` and are excluded from version control.
