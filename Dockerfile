# Use Python 3.12 slim image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install uv for fast package management
COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /uvx /bin/

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ src/

# Install dependencies using uv
RUN uv pip install --system .

# Expose the default port
EXPOSE 8000

# Set environment variables
ENV HOST=0.0.0.0
ENV PORT=8000

# Run the server
CMD ["python", "-m", "mcp_server_oauth_toy"]
