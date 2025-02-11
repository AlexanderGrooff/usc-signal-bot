FROM python:3.12-slim

# Install system dependencies for Signal and curl for healthcheck
RUN apt-get update && apt-get install -y \
    build-essential \
    libssl-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 signalbot

# Set working directory and create necessary directories
WORKDIR /app
RUN mkdir -p /app && chown -R signalbot:signalbot /app

# Copy project files
COPY pyproject.toml README.md main.py /app/
COPY usc_signal_bot/ /app/usc_signal_bot/

# Install dependencies and project
RUN pip install --no-cache-dir .

# Switch to non-root user
USER signalbot

# Command to run the bot
CMD ["python", "main.py"]
