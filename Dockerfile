FROM python:3.14-slim

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml ./

# Install production dependencies
RUN pip install --no-cache-dir .

# Copy application code
COPY app/ app/

# Create data directory for SQLite
RUN mkdir -p data

# Railway injects $PORT at runtime; fall back to 8000 for local development
EXPOSE ${PORT:-8000}

CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
