# Pin Python to the age-qualified 3.12.14 slim image.
FROM ghcr.io/astral-sh/uv:0.13.4@sha256:9f130421e930bfbdc563c00740466603f8723158e90297d07957c2294640262b AS uv
FROM python:3.12.14-slim-trixie@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f

# Set working directory
WORKDIR /app

# Install uv for fast package management
COPY --from=uv /uv /uvx /bin/

# Copy project files
COPY pyproject.toml README.md uv.toml ./
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
