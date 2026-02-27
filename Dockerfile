FROM python:3.14-slim

WORKDIR /app

# Copy dependency file and create minimal package stub for setuptools
# so dependencies can be installed in a cached layer
COPY pyproject.toml ./
RUN mkdir -p app && touch app/__init__.py \
    && pip install --no-cache-dir . \
    && rm -rf app

# Copy application code
COPY app/ app/

# Create data directory for SQLite
RUN mkdir -p data

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
