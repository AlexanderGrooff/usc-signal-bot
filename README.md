# USC Signal Bot

## Overview

This is a Signal messenger bot that can process commands from chat, deployed in Kubernetes.

It's used to make reservations at the USC gyms.

## Usage

To use the bot, you need to register it as a device with Signal. To do this you put the `signal-api` service in `MODE=normal` and go to http://localhost:8080/v1/qrcodelink?device_name=signal-api.
Register the device with Signal by scanning the QR code with the Signal app on your phone.

When you're done, put the `signal-api` service in `MODE=json-rpc` and restart it.

## Development

### Prerequisites

- Python 3.12
- [uv](https://github.com/astral-sh/uv) (Python package manager)
- Docker and Docker Compose
- direnv

### Setup

1. Install uv (if not already installed):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. Install dependencies:
   ```bash
   uv sync
   ```

3. Activate the virtual environment:
   ```bash
   source .venv/bin/activate  # On Linux/macOS
   # or
   .venv\Scripts\activate  # On Windows
   ```

4. Install the project in editable mode:
   ```bash
   uv pip install -e .
   ```

For development with dev dependencies:
```bash
uv sync --extra dev
```
