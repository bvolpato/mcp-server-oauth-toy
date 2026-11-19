FROM ghcr.io/astral-sh/uv:0.13.8@sha256:5cc1805e2426484abca4ad46ea783bab281fdb225fd82d8ce6d66a81254bac85 AS uv
FROM python:3.15.0-slim-trixie@sha256:f5b92f2a669a4c347044f29367f31983280b648250ca94dea66f98c53bc87e58

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
