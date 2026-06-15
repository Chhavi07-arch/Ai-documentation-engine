# --- AI Documentation Engine — backend image ---
FROM python:3.11-slim

# Git is required by GitPython to clone repositories.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Storage directories (also configurable via env).
RUN mkdir -p /data/repositories /data/docs_storage /data/vector_storage
ENV REPOSITORIES_DIR=/data/repositories \
    DOCS_STORAGE_DIR=/data/docs_storage \
    VECTOR_STORAGE_DIR=/data/vector_storage \
    DATABASE_URL=sqlite:////data/docengine.db

EXPOSE 8000

# Platforms like Render/Railway inject $PORT; default to 8000 locally.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
