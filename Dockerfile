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

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
