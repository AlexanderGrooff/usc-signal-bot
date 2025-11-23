# Build stage - contains build tools and installs dependencies
FROM python:3.12-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libssl-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy git data for version generation (only in build stage)
COPY .git/ /app/.git/

# Copy project files needed for installation
COPY pyproject.toml README.md /app/
COPY usc_signal_bot/ /app/usc_signal_bot/

# Install dependencies and project using uv (this will generate _version.py with git)
RUN uv pip install --system --no-cache . && \
    rm -rf /app/.git

# Runtime stage - minimal image with only runtime dependencies
FROM python:3.12-slim

# Install only runtime system dependencies and create user in one layer
RUN apt-get update && apt-get install -y --no-install-recommends \
    libssl3 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 signalbot

# Set working directory
WORKDIR /app

# Copy installed Python packages from builder stage
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code and generated version file, then set ownership
COPY --chown=signalbot:signalbot main.py /app/
COPY --chown=signalbot:signalbot usc_signal_bot/ /app/usc_signal_bot/
COPY --chown=signalbot:signalbot --from=builder /app/usc_signal_bot/_version.py /app/usc_signal_bot/_version.py

# Switch to non-root user
USER signalbot

# Command to run the bot
CMD ["python", "main.py"]
