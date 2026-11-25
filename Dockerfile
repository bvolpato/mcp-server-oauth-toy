FROM ghcr.io/astral-sh/uv:0.13.9@sha256:d3b601f0c7b118bc1753febf7c41cc80981df678445e0254284eecf84db79a7d AS uv
FROM python:3.15.2-slim-trixie@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928

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
