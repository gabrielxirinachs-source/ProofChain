# ─────────────────────────────────────────────────────────
# Multi-stage build:
#   Stage 1 (builder) — install dependencies
#   Stage 2 (runtime) — lean final image
#
# Why multi-stage? Keeps the final Docker image small by
# not shipping build tools (gcc, pip cache, etc.) to prod.
# ─────────────────────────────────────────────────────────

# Stage 1: Install dependencies
FROM python:3.11-slim AS builder

WORKDIR /app

# Install system deps needed to compile some Python packages
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --prefix=/install -r requirements.txt

# ─────────────────────────────────────────────────────────
# Stage 2: Runtime image
# ─────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Copy only the installed packages from builder
COPY --from=builder /install /usr/local
# System lib needed at runtime for psycopg2
RUN apt-get update && apt-get install -y libpq5 && rm -rf /var/lib/apt/lists/*

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]