# Changelog

All notable changes to the AI Documentation Engine are documented here.
This project follows [Semantic Versioning](https://semver.org/).

## [2.0.0]

### Added
- **GitHub webhook** (`POST /api/github/webhook`) — HMAC-verified push handler
  that incrementally fetches new commits (no re-clone) and runs change
  detection automatically. Gated behind `GITHUB_WEBHOOK_SECRET`.
- **Manual sync** (`POST /api/sync-and-detect`) — pull latest commits and detect
  changes without a public webhook URL.
- **Incremental fetch** (`git_utils.fetch_latest`) — shallow fetch + reset of an
  existing clone, downloading only new objects.
- **Documentation-file tracking** — `*.md` / `*.rst` files (e.g. `README.md`) are
  now fingerprinted and diffed, so content edits surface as staleness flags.

### Changed
- Baselines and change detection share one `EntityState` builder
  (`app/services/states.py`) covering both code entities and doc files.

## [1.0.0]

### Added
- GitHub repository ingestion (clone → AST parse → persist) for Python projects.
- AI documentation generation with a deterministic offline fallback.
- RAG pipeline (chunking, embeddings, ChromaDB) with grounded chat over docs.
- AST-aware change detection, structural diffing, and staleness flags.
- Next.js frontend: repositories, docs, chat, and staleness views.

### Fixed
- `POST /api/generate-docs` no longer crashes with a `UNIQUE constraint failed`
  error; documentation persistence is now a reliable upsert.
- SQLite WAL/SHM runtime files are no longer tracked by git.
