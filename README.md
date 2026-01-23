# MCP Server OAuth Toy

A simple MCP (Model Context Protocol) server with OAuth 2.0 authentication for testing the OAuth support in [mcp-cli](https://github.com/philschmid/mcp-cli).

## Features

- Full OAuth 2.0 Authorization Code flow with PKCE
- Dynamic client registration (RFC 7591)
- In-memory session storage (for testing)
- Browser-based authorization where users enter their name
- Two tools: `whoami` (returns authenticated user) and `echo` (echoes message with user name)

## Quick Start

### 1. Start the Server (Docker)

```bash
# Clone the repository
git clone https://github.com/bvolpato/mcp-server-oauth-toy.git
cd mcp-server-oauth-toy

# Build and run with Docker
docker build -t mcp-server-oauth-toy .
docker run -p 8000:8000 mcp-server-oauth-toy
```

### 2. Configure mcp-cli

Add to your `~/.config/mcp/mcp_servers.json`:

```json
{
  "mcpServers": {
    "oauth-toy": {
      "url": "http://localhost:8000/mcp",
      "oauth": true
    }
  }
}
```

### 3. Test with mcp-cli

```bash
# Install mcp-cli (requires Bun)
bun install -g @philschmid/mcp-cli

# List available tools (will trigger OAuth flow on first run)
mcp-cli -c ~/.config/mcp/mcp_servers.json oauth-toy

# Call the whoami tool
mcp-cli -c ~/.config/mcp/mcp_servers.json oauth-toy/whoami '{}'

# Call the echo tool
mcp-cli -c ~/.config/mcp/mcp_servers.json oauth-toy/echo '{"message": "Hello!"}'
```

## OAuth Flow

When you first connect to the server:

1. mcp-cli detects the server requires OAuth (401 response)
2. mcp-cli discovers OAuth endpoints via `/.well-known/oauth-authorization-server`
3. mcp-cli registers as a client via `/register` (dynamic registration)
4. Your browser opens to the authorization page
5. You enter your name and click "Authorize"
6. mcp-cli receives the authorization code and exchanges it for tokens
7. Subsequent requests use the stored access token

## Tools

### `whoami`

Returns the name of the authenticated user.

```bash
mcp-cli -c ~/.config/mcp/mcp_servers.json oauth-toy/whoami '{}'
# Output: You are authenticated as: Alice
```

### `echo`

Echoes back the provided message with the authenticated user's name.

```bash
mcp-cli -c ~/.config/mcp/mcp_servers.json oauth-toy/echo '{"message": "Hello!"}'
# Output: Alice says: Hello!
```

## Local Development

### Using uv

```bash
# Install dependencies
uv sync

# Run the server
uv run python -m mcp_server_oauth_toy
```

### Using Docker Compose

```bash
docker-compose up
```

## OAuth Endpoints

| Endpoint | Description |
|----------|-------------|
| `/.well-known/oauth-authorization-server` | OAuth 2.0 Authorization Server Metadata |
| `/register` | Dynamic Client Registration |
| `/authorize` | Authorization endpoint (shows login form) |
| `/token` | Token endpoint |

## MCP Endpoints

| Endpoint | Description |
|----------|-------------|
| `/mcp` | MCP over Streamable HTTP |
| `/health` | Health check |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Server host |
| `PORT` | `8000` | Server port |
| `BASE_URL` | `http://localhost:8000` | Public base URL |
| `REDIS_URL` | (none) | Redis URL for persistent storage (e.g., Upstash) |
| `KV_URL` | (none) | Alternative Redis URL (Vercel KV) |

## Persistent Storage (for Serverless)

By default, the server uses in-memory storage which doesn't persist across serverless function invocations. For production use on Vercel, set up Redis:

### Using Upstash (Recommended)

1. Create a free Redis database at [upstash.com](https://upstash.com)
2. Copy the `UPSTASH_REDIS_REST_URL` 
3. Add it as `REDIS_URL` in your Vercel environment variables

### Using Vercel KV

1. Add Vercel KV to your project from the Vercel dashboard
2. The `KV_URL` environment variable is automatically set

## Testing the PR

This server was created to test [mcp-cli PR #18](https://github.com/philschmid/mcp-cli/pull/18) which adds OAuth support.

To test the OAuth implementation:

1. Start this server locally
2. Use mcp-cli with the `oauth: true` configuration
3. Complete the browser-based authorization
4. Verify the `whoami` tool returns your name

## Deploy to Vercel

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2Fbvolpato%2Fmcp-server-oauth-toy)

1. Click the button above or import the repo at [vercel.com/new](https://vercel.com/new)
2. Select **"Other"** as the framework (Vercel auto-detects Python)
3. Deploy!

The `BASE_URL` is automatically set from `VERCEL_URL`.

Then update your mcp_servers.json:

```json
{
  "mcpServers": {
    "oauth-toy": {
      "url": "https://your-deployment.vercel.app/mcp",
      "oauth": true
    }
  }
}
```

## License

MIT
