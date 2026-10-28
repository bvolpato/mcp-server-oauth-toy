"""
Main server module - combines OAuth and MCP functionality.

This server exposes:
- OAuth 2.0 endpoints (authorization, token, etc.)
- MCP endpoints (tools listing, tool calls)
- A simple authorization UI where users can enter their name
"""

import hashlib
import json
import logging
import os
import secrets
import sys
import time
from base64 import urlsafe_b64encode
from typing import Any
from urllib.parse import urlencode

import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Route

from .storage import (
    AccessToken,
    AuthorizationCode,
    PendingAuthorization,
    RefreshToken,
    create_oauth_store,
    ACCESS_TOKEN_EXPIRY,
)

logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)
logger = logging.getLogger(__name__)

# ============================================================================
# Configuration
# ============================================================================

# Server settings
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))
BASE_URL = os.environ.get("BASE_URL", f"http://localhost:{PORT}")

# Global store (created lazily)
_oauth_store = None


def get_oauth_store():
    """Get or create the OAuth store."""
    global _oauth_store
    if _oauth_store is None:
        _oauth_store = create_oauth_store()
    return _oauth_store

# ============================================================================
# OAuth 2.0 Endpoints
# ============================================================================


def generate_token(length: int = 32) -> str:
    """Generate a cryptographically secure random token."""
    return secrets.token_urlsafe(length)


def verify_pkce(code_verifier: str, code_challenge: str, method: str) -> bool:
    """Verify PKCE code challenge."""
    if method == "plain":
        return code_verifier == code_challenge
    elif method == "S256":
        # SHA256 hash, base64url encoded
        digest = hashlib.sha256(code_verifier.encode()).digest()
        computed = urlsafe_b64encode(digest).rstrip(b"=").decode()
        return computed == code_challenge
    return False


async def oauth_metadata(request: Request) -> JSONResponse:
    """OAuth 2.0 Authorization Server Metadata (RFC 8414)."""
    base_url = BASE_URL.rstrip("/")
    return JSONResponse(
        {
            "issuer": base_url,
            "authorization_endpoint": f"{base_url}/authorize",
            "token_endpoint": f"{base_url}/token",
            "registration_endpoint": f"{base_url}/register",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256", "plain"],
            "token_endpoint_auth_methods_supported": ["none", "client_secret_post"],
            "scopes_supported": ["mcp"],
        }
    )


async def register_client(request: Request) -> JSONResponse:
    """OAuth 2.0 Dynamic Client Registration (RFC 7591)."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_request"}, status_code=400)

    # Generate client credentials
    client_id = generate_token(16)

    # Store client info
    client_info = {
        "client_id": client_id,
        "client_name": body.get("client_name", "Unknown Client"),
        "redirect_uris": body.get("redirect_uris", ["http://localhost/callback"]),
        "grant_types": body.get("grant_types", ["authorization_code", "refresh_token"]),
        "response_types": body.get("response_types", ["code"]),
        "token_endpoint_auth_method": body.get(
            "token_endpoint_auth_method", "none"
        ),
    }

    get_oauth_store().register_client(client_id, client_info)

    logger.info(f"Registered new client: {client_id}")

    return JSONResponse(
        {
            "client_id": client_id,
            "client_name": client_info["client_name"],
            "redirect_uris": client_info["redirect_uris"],
            "grant_types": client_info["grant_types"],
            "response_types": client_info["response_types"],
            "token_endpoint_auth_method": client_info["token_endpoint_auth_method"],
        },
        status_code=201,
    )


def authorization_page_html(auth_id: str, client_name: str) -> str:
    """Generate the authorization page HTML."""
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>MCP OAuth Toy - Authorization</title>
    <style>
        * {{
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }}
        .container {{
            text-align: center;
            padding: 40px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 16px;
            backdrop-filter: blur(10px);
            max-width: 400px;
            width: 90%;
        }}
        h1 {{
            margin: 0 0 8px 0;
            font-size: 24px;
        }}
        .subtitle {{
            margin: 0 0 24px 0;
            opacity: 0.9;
            font-size: 14px;
        }}
        .client-name {{
            background: rgba(255, 255, 255, 0.2);
            padding: 8px 16px;
            border-radius: 8px;
            margin-bottom: 24px;
            font-weight: 500;
        }}
        .form-group {{
            margin-bottom: 20px;
            text-align: left;
        }}
        label {{
            display: block;
            margin-bottom: 8px;
            font-weight: 500;
        }}
        input[type="text"] {{
            width: 100%;
            padding: 12px 16px;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            background: rgba(255, 255, 255, 0.9);
            color: #333;
        }}
        input[type="text"]:focus {{
            outline: 2px solid rgba(255, 255, 255, 0.5);
        }}
        button {{
            width: 100%;
            padding: 12px 24px;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            background: white;
            color: #667eea;
            transition: transform 0.1s, box-shadow 0.1s;
        }}
        button:hover {{
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
        }}
        button:active {{
            transform: translateY(0);
        }}
        .info {{
            margin-top: 24px;
            font-size: 12px;
            opacity: 0.8;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔐 MCP OAuth Toy</h1>
        <p class="subtitle">Test OAuth Authentication</p>
        
        <div class="client-name">
            Authorizing: {client_name}
        </div>
        
        <form method="POST" action="/authorize/complete">
            <input type="hidden" name="auth_id" value="{auth_id}">
            
            <div class="form-group">
                <label for="user_name">Enter your name:</label>
                <input type="text" id="user_name" name="user_name" 
                       placeholder="e.g., Alice" required autofocus>
            </div>
            
            <button type="submit">Authorize</button>
        </form>
        
        <p class="info">
            This name will be returned by the 'whoami' tool.
        </p>
    </div>
</body>
</html>"""


async def authorize(request: Request) -> Response:
    """OAuth 2.0 Authorization Endpoint."""
    params = dict(request.query_params)

    response_type = params.get("response_type")
    client_id = params.get("client_id")
    redirect_uri = params.get("redirect_uri", "http://localhost/callback")
    scope = params.get("scope", "mcp")
    state = params.get("state", "")
    code_challenge = params.get("code_challenge")
    code_challenge_method = params.get("code_challenge_method", "S256")

    logger.info(f"Authorization request: client_id={client_id}, redirect_uri={redirect_uri}")

    # Validate request
    if response_type != "code":
        return JSONResponse(
            {"error": "unsupported_response_type"}, status_code=400
        )

    if not client_id:
        return JSONResponse({"error": "invalid_request", "error_description": "client_id required"}, status_code=400)

    if not code_challenge:
        return JSONResponse(
            {"error": "invalid_request", "error_description": "PKCE code_challenge required"},
            status_code=400,
        )

    # Store pending authorization
    auth_id = generate_token(16)
    pending = PendingAuthorization(
        client_id=client_id,
        redirect_uri=redirect_uri,
        scope=scope,
        state=state,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
    )
    get_oauth_store().store_pending_auth(auth_id, pending)

    # Get client name for display
    client = get_oauth_store().get_client(client_id)
    client_name = client.get("client_name", client_id) if client else client_id

    # Show authorization page
    return HTMLResponse(authorization_page_html(auth_id, client_name))


async def authorize_complete(request: Request) -> Response:
    """Complete the authorization (user submitted the form)."""
    try:
        form = await request.form()
    except Exception:
        return JSONResponse({"error": "invalid_request"}, status_code=400)

    auth_id = form.get("auth_id")
    user_name = form.get("user_name", "").strip()

    if not auth_id or not user_name:
        return JSONResponse(
            {"error": "invalid_request", "error_description": "auth_id and user_name required"},
            status_code=400,
        )

    # Get pending authorization
    pending = get_oauth_store().get_pending_auth(auth_id)
    if not pending:
        return HTMLResponse(
            "<h1>Error</h1><p>Authorization request expired or not found.</p>",
            status_code=400,
        )

    # Remove pending auth
    get_oauth_store().remove_pending_auth(auth_id)

    # Generate authorization code
    code = generate_token(32)
    auth_code = AuthorizationCode(
        code=code,
        client_id=pending.client_id,
        redirect_uri=pending.redirect_uri,
        scope=pending.scope,
        state=pending.state,
        code_challenge=pending.code_challenge,
        code_challenge_method=pending.code_challenge_method,
        user_name=user_name,
    )
    get_oauth_store().store_auth_code(auth_code)

    logger.info(f"Generated auth code for user: {user_name}")

    # Redirect back to client
    redirect_params = {"code": code}
    if pending.state:
        redirect_params["state"] = pending.state

    redirect_url = f"{pending.redirect_uri}?{urlencode(redirect_params)}"
    
    # Return HTML that redirects (handles localhost:80 better than 302)
    return HTMLResponse(f"""<!DOCTYPE html>
<html>
<head>
    <meta http-equiv="refresh" content="0;url={redirect_url}">
    <title>Redirecting...</title>
</head>
<body>
    <p>Redirecting to application...</p>
    <script>window.location.href = "{redirect_url}";</script>
</body>
</html>""")


async def token(request: Request) -> JSONResponse:
    """OAuth 2.0 Token Endpoint."""
    try:
        form = await request.form()
        body = {k: v for k, v in form.items()}
    except Exception:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid_request"}, status_code=400)

    grant_type = body.get("grant_type")
    logger.info(f"Token request: grant_type={grant_type}")

    if grant_type == "authorization_code":
        return await handle_authorization_code_grant(body)
    elif grant_type == "refresh_token":
        return await handle_refresh_token_grant(body)
    else:
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)


async def handle_authorization_code_grant(body: dict) -> JSONResponse:
    """Handle authorization_code grant type."""
    code = body.get("code")
    redirect_uri = body.get("redirect_uri")
    client_id = body.get("client_id")
    code_verifier = body.get("code_verifier")

    if not all([code, client_id, code_verifier]):
        return JSONResponse(
            {"error": "invalid_request", "error_description": "Missing required parameters"},
            status_code=400,
        )

    # Get and consume authorization code
    auth_code = get_oauth_store().consume_auth_code(code)
    if not auth_code:
        return JSONResponse(
            {"error": "invalid_grant", "error_description": "Invalid or expired authorization code"},
            status_code=400,
        )

    # Verify client
    if auth_code.client_id != client_id:
        return JSONResponse(
            {"error": "invalid_grant", "error_description": "Client ID mismatch"},
            status_code=400,
        )

    # Verify PKCE
    if not verify_pkce(
        code_verifier, auth_code.code_challenge, auth_code.code_challenge_method
    ):
        return JSONResponse(
            {"error": "invalid_grant", "error_description": "PKCE verification failed"},
            status_code=400,
        )

    # Generate tokens
    access_token = AccessToken(
        token=generate_token(32),
        client_id=client_id,
        user_name=auth_code.user_name,
        scope=auth_code.scope,
    )
    get_oauth_store().store_access_token(access_token)

    refresh_token = RefreshToken(
        token=generate_token(32),
        client_id=client_id,
        user_name=auth_code.user_name,
        scope=auth_code.scope,
    )
    get_oauth_store().store_refresh_token(refresh_token)

    logger.info(f"Issued tokens for user: {auth_code.user_name}")

    return JSONResponse(
        {
            "access_token": access_token.token,
            "token_type": "Bearer",
            "expires_in": ACCESS_TOKEN_EXPIRY,
            "refresh_token": refresh_token.token,
            "scope": auth_code.scope,
        }
    )


async def handle_refresh_token_grant(body: dict) -> JSONResponse:
    """Handle refresh_token grant type."""
    refresh_token_str = body.get("refresh_token")
    client_id = body.get("client_id")

    if not refresh_token_str:
        return JSONResponse(
            {"error": "invalid_request", "error_description": "refresh_token required"},
            status_code=400,
        )

    # Get refresh token
    refresh_token = get_oauth_store().get_refresh_token(refresh_token_str)
    if not refresh_token:
        return JSONResponse(
            {"error": "invalid_grant", "error_description": "Invalid or expired refresh token"},
            status_code=400,
        )

    # Verify client if provided
    if client_id and refresh_token.client_id != client_id:
        return JSONResponse(
            {"error": "invalid_grant", "error_description": "Client ID mismatch"},
            status_code=400,
        )

    # Revoke old refresh token
    get_oauth_store().revoke_refresh_token(refresh_token_str)

    # Generate new tokens
    access_token = AccessToken(
        token=generate_token(32),
        client_id=refresh_token.client_id,
        user_name=refresh_token.user_name,
        scope=refresh_token.scope,
    )
    get_oauth_store().store_access_token(access_token)

    new_refresh_token = RefreshToken(
        token=generate_token(32),
        client_id=refresh_token.client_id,
        user_name=refresh_token.user_name,
        scope=refresh_token.scope,
    )
    get_oauth_store().store_refresh_token(new_refresh_token)

    logger.info(f"Refreshed tokens for user: {refresh_token.user_name}")

    return JSONResponse(
        {
            "access_token": access_token.token,
            "token_type": "Bearer",
            "expires_in": ACCESS_TOKEN_EXPIRY,
            "refresh_token": new_refresh_token.token,
            "scope": refresh_token.scope,
        }
    )


def get_bearer_token(request: Request) -> str | None:
    """Extract Bearer token from Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


def validate_token(request: Request) -> AccessToken | None:
    """Validate the access token from the request."""
    token = get_bearer_token(request)
    if not token:
        return None
    return get_oauth_store().get_access_token(token)


# ============================================================================
# MCP Server
# ============================================================================

# List tools using the MCP SDK 2 low-level handler API.
async def handle_list_tools(
    _ctx: Any, _params: types.PaginatedRequestParams | None
) -> types.ListToolsResult:
    """List available tools."""
    return types.ListToolsResult(tools=[
        types.Tool(
            name="whoami",
            description="Returns the name of the authenticated user. Use this to verify OAuth authentication is working.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        types.Tool(
            name="echo",
            description="Echoes back the provided message with the authenticated user's name.",
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The message to echo back",
                    }
                },
                "required": ["message"],
            },
        ),
    ])


# Store for per-request user context
_request_user_name: str | None = None


async def handle_call_tool(
    _ctx: Any, params: types.CallToolRequestParams
) -> types.CallToolResult:
    """Handle tool calls."""
    global _request_user_name
    name = params.name
    arguments = params.arguments

    if name == "whoami":
        if _request_user_name:
            return types.CallToolResult(content=[
                types.TextContent(
                    type="text",
                    text=f"You are authenticated as: {_request_user_name}",
                )
            ])
        else:
            return types.CallToolResult(content=[
                types.TextContent(
                    type="text",
                    text="Error: Not authenticated or user context not available",
                )
            ])

    elif name == "echo":
        message = (arguments or {}).get("message", "")
        if _request_user_name:
            return types.CallToolResult(content=[
                types.TextContent(
                    type="text",
                    text=f"{_request_user_name} says: {message}",
                )
            ])
        else:
            return types.CallToolResult(content=[
                types.TextContent(
                    type="text",
                    text=f"Anonymous says: {message}",
                )
            ])

    else:
        return types.CallToolResult(content=[
            types.TextContent(
                type="text",
                text=f"Unknown tool: {name}",
            )
        ])


# Create MCP server instance with constructor-registered handlers.
mcp_server = Server(
    "mcp-server-oauth-toy",
    on_list_tools=handle_list_tools,
    on_call_tool=handle_call_tool,
)


# ============================================================================
# SSE Transport with OAuth
# ============================================================================


async def handle_sse(request: Request) -> Response:
    """Handle SSE connection for MCP with OAuth validation."""
    global _request_user_name

    # Validate OAuth token
    access_token = validate_token(request)
    if not access_token:
        return JSONResponse(
            {"error": "unauthorized", "error_description": "Valid access token required"},
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Set user context for this request
    _request_user_name = access_token.user_name
    logger.info(f"SSE connection from user: {access_token.user_name}")

    # Create SSE transport
    sse = SseServerTransport("/messages/")

    async with sse.connect_sse(
        request.scope, request.receive, request._send
    ) as streams:
        await mcp_server.run(
            streams[0],
            streams[1],
            InitializationOptions(
                server_name="mcp-server-oauth-toy",
                server_version="0.1.0",
                capabilities=mcp_server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

    return Response()


async def handle_messages(request: Request) -> Response:
    """Handle POST messages for SSE transport."""
    global _request_user_name

    # Validate OAuth token
    access_token = validate_token(request)
    if not access_token:
        return JSONResponse(
            {"error": "unauthorized", "error_description": "Valid access token required"},
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Set user context
    _request_user_name = access_token.user_name

    # This endpoint receives messages from the client
    # The SSE transport handles this internally
    return Response(status_code=202)


# ============================================================================
# Streamable HTTP Transport with OAuth
# ============================================================================


async def handle_mcp(request: Request) -> Response:
    """Handle MCP requests over streamable HTTP transport with OAuth."""
    global _request_user_name

    # Validate OAuth token
    access_token = validate_token(request)
    if not access_token:
        logger.warning("Unauthorized MCP request - no valid token")
        return JSONResponse(
            {"error": "unauthorized", "error_description": "Valid access token required"},
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Set user context for this request
    _request_user_name = access_token.user_name
    logger.info(f"MCP request from user: {access_token.user_name}")

    # Handle the MCP request
    try:
        body = await request.body()
        body_json = json.loads(body) if body else {}
        logger.debug(f"MCP request body: {body_json}")

        # Handle JSON-RPC request
        method = body_json.get("method", "")
        req_id = body_json.get("id")

        if method == "initialize":
            response = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {
                        "name": "mcp-server-oauth-toy",
                        "version": "0.1.0",
                    },
                    "capabilities": {
                        "tools": {"listChanged": False},
                    },
                },
            }
        elif method == "notifications/initialized":
            # This is a notification, no response needed
            return Response(status_code=202)
        elif method == "tools/list":
            tools = await handle_list_tools()
            response = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": [
                        {
                            "name": t.name,
                            "description": t.description,
                            "inputSchema": t.inputSchema,
                        }
                        for t in tools
                    ]
                },
            }
        elif method == "tools/call":
            params = body_json.get("params", {})
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {})
            result = await handle_call_tool(tool_name, tool_args)
            response = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {"type": c.type, "text": c.text} for c in result
                    ]
                },
            }
        else:
            response = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}",
                },
            }

        return JSONResponse(response)

    except Exception as e:
        logger.exception("Error handling MCP request")
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": str(e)},
            },
            status_code=500,
        )


# ============================================================================
# Health Check
# ============================================================================


async def health(request: Request) -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse({"status": "ok", "server": "mcp-server-oauth-toy"})


# ============================================================================
# Application Setup
# ============================================================================


def create_app() -> Starlette:
    """Create the Starlette application."""
    routes = [
        # Health
        Route("/health", health, methods=["GET"]),
        # OAuth 2.0
        Route("/.well-known/oauth-authorization-server", oauth_metadata, methods=["GET"]),
        Route("/register", register_client, methods=["POST"]),
        Route("/authorize", authorize, methods=["GET"]),
        Route("/authorize/complete", authorize_complete, methods=["POST"]),
        Route("/token", token, methods=["POST"]),
        # MCP (Streamable HTTP)
        Route("/mcp", handle_mcp, methods=["GET", "POST"]),
        # MCP (SSE - alternative transport)
        Route("/sse", handle_sse, methods=["GET"]),
        Route("/messages/", handle_messages, methods=["POST"]),
    ]

    middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        ),
    ]

    return Starlette(routes=routes, middleware=middleware)


def main():
    """Main entry point."""
    import uvicorn

    app = create_app()
    logger.info(f"Starting MCP OAuth Toy server on {HOST}:{PORT}")
    logger.info(f"Base URL: {BASE_URL}")
    logger.info(f"OAuth metadata: {BASE_URL}/.well-known/oauth-authorization-server")
    logger.info(f"MCP endpoint: {BASE_URL}/mcp")

    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
